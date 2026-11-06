#!/usr/bin/env bash
# Task 4 evidence. Each part writes into results/ (see README "Evidence").
set -uo pipefail
source scripts/lib.sh
K="kubectl -n app"
PART="${1:-all}"

part() { [ "$PART" = all ] || [ "$PART" = "$1" ]; }

if part resources; then
  say "4.1-4.4 objects, requests/limits, probes, HPA"
  $K get deploy,rs,pods,svc,endpoints,ingress,hpa -o wide
  $K get deploy kd-service -o jsonpath='{.spec.template.spec.containers[0].resources}{"\n"}{.spec.template.spec.containers[0].readinessProbe}{"\n"}{.spec.template.spec.containers[0].livenessProbe}{"\n"}'
  say "/parse through the Ingress (localhost:8080)"
  curl -si -X POST localhost:8080/parse -H 'content-type: application/json' -d '{"text":"what is the weather in london"}'; echo
fi

if part coldstart; then
  say "4.7 cold start x3 (delete all pods; endpoints empty until model loaded)"
  : > results/coldstart_times.txt
  for run in 1 2 3; do
    t0=$(date +%s)
    $K delete pods -l app=kd-service --wait=false
    sleep 1
    for i in $(seq 1 90); do
      eps=$($K get endpoints kd-service -o jsonpath='{.subsets[*].addresses[*].ip}')
      st=$($K get pods -l app=kd-service --no-headers 2>/dev/null | awk '{print $1":"$2":"$3}' | tr '\n' ' ')
      echo "$(ts) run$run ready-endpoints=[${eps}] pods: $st"
      if [ -n "$eps" ] && $K get pods -l app=kd-service --no-headers | awk '$3=="Running" && $2 ~ /^1\/1/' | grep -q .; then
        n_new_ready=$($K get pods -l app=kd-service -o json | python3 scripts/pod_times.py "$t0" | wc -l)
        [ "$n_new_ready" -ge 1 ] && break
      fi
      sleep 1
    done
    wait_ready_replicas "$($K get deploy kd-service -o jsonpath='{.spec.replicas}')"
    $K get pods -l app=kd-service -o json | python3 scripts/pod_times.py "$t0" | sed "s/^/run$run /" | tee -a results/coldstart_times.txt
    pod=$($K get pods -l app=kd-service -o name | head -1)
    echo "--- logs $pod (model download)"; $K logs "$pod" | grep -E "Downloading|downloaded|download complete|ready" | tee "results/coldstart_run${run}_log.txt"
    sleep 5
  done
  python3 - <<'PY'
import statistics
rows = [l.split() for l in open("results/coldstart_times.txt") if l.strip()]
per_run = {}
for run, pod, sec in rows:
    per_run.setdefault(run, []).append(int(sec))
vals = [max(v) for v in per_run.values()]
print("per-run cold start (s, slowest pod per run):", vals, " median:", statistics.median(vals))
open("results/coldstart_summary.txt", "w").write(f"per_run_seconds={vals}\nmedian_seconds={statistics.median(vals)}\n")
PY
fi

if part hpa; then
  say "4.4 HPA: wait for 1 replica, load, scale to 2, back to 1"
  $K patch hpa kd-service --type merge -p '{"spec":{"minReplicas":1}}'
  for i in $(seq 1 60); do r=$($K get deploy kd-service -o jsonpath='{.status.replicas}'); [ "$r" = 1 ] && break; sleep 10; done
  ( for i in $(seq 1 75); do echo "$(ts) $($K get hpa kd-service --no-headers)"; sleep 8; done ) > results/hpa_watch.txt &
  W=$!
  run_locust hpa_load 4m
  sleep 150
  kill $W 2>/dev/null; cat results/hpa_watch.txt
  $K describe hpa kd-service | tail -15 | tee results/hpa_events.txt
fi

if part lb; then
  say "4.8 load balancing with exactly two Ready replicas (minReplicas temporarily 2)"
  $K patch hpa kd-service --type merge -p '{"spec":{"minReplicas":2}}'
  wait_ready_replicas 2; $K get pods -l app=kd-service -o wide
  run_locust lb_test 2m
fi

if part rolling; then
  say "4.5 rolling update v1 -> v2 under load, then rollout undo"
  $K patch hpa kd-service --type merge -p '{"spec":{"minReplicas":2}}'
  wait_ready_replicas 2
  ( LOADTEST_HEADERS_OUT=results/rolling_headers.json locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 \
      --run-time 6m --host "$LOCUST_HOST" --csv results/rolling > results/rolling_locust.log 2>&1 ) &
  L=$!
  sleep 30
  $K set env deployment/kd-service MODEL_URI=s3://models/v2 MODEL_VERSION=v2
  $K rollout status deploy/kd-service --timeout=300s
  for i in 1 2 3; do curl -s -D - -o /dev/null -X POST localhost:8080/parse -H 'content-type: application/json' -d '{"text":"wake me at six am"}' | grep -i x-model-version; done
  sleep 30
  $K rollout history deploy/kd-service
  $K rollout undo deploy/kd-service
  $K rollout status deploy/kd-service --timeout=300s
  wait $L
  python3 scripts/locust_summary.py results/rolling
  say "after rollback"
  for i in 1 2 3; do curl -s -D - -o /dev/null -X POST localhost:8080/parse -H 'content-type: application/json' -d '{"text":"wake me at six am"}' | grep -i x-model-version; done
  $K get deploy kd-service -o jsonpath='{.spec.template.spec.containers[0].env}{"\n"}'
fi

if part recovery; then
  say "4.6 recovery: delete one pod under load"
  wait_ready_replicas 2
  ( LOADTEST_HEADERS_OUT=results/recovery_headers.json locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 \
      --run-time 3m --host "$LOCUST_HOST" --csv results/recovery > results/recovery_locust.log 2>&1 ) &
  L=$!
  sleep 30
  victim=$($K get pods -l app=kd-service -o name | head -1)
  echo "$(ts) deleting $victim"; $K delete "$victim" --wait=false
  for i in $(seq 1 45); do echo "$(ts) $($K get deploy kd-service --no-headers)"; sleep 2; done
  wait $L
  python3 scripts/locust_summary.py results/recovery
  $K get pods -l app=kd-service -o wide
fi

if [ "$PART" = all ] || [ "$PART" = restore ]; then
  $K patch hpa kd-service --type merge -p '{"spec":{"minReplicas":1}}'
  $K get hpa kd-service
fi
