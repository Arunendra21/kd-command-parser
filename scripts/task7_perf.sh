#!/usr/bin/env bash
# Task 7: the standard load test against the Ingress, with kubectl top sampled during the run.
set -uo pipefail
source scripts/lib.sh
say "state before"; kubectl -n app get deploy,hpa,pods -o wide
( for i in $(seq 1 14); do echo "--- $(ts)"; kubectl top pods -n app --no-headers; kubectl -n app get hpa kd-service --no-headers; sleep 10; done ) > results/task7_top.txt 2>&1 &
T=$!
say "standard command"
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host "${LOCUST_HOST:-http://localhost:8080}" --csv results/loadtest \
  2>&1 | tee results/loadtest_locust.log || true
wait $T
python3 scripts/locust_summary.py results/loadtest
cat results/task7_top.txt
python3 scripts/cost.py results/loadtest_summary.json k8s/app/deployment.yaml data/rate_card.json | tee results/cost.txt
