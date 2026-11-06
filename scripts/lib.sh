# Shared helpers for the evidence scripts.
ts() { date '+%H:%M:%S'; }
say() { echo; echo "===== [$(ts)] $*"; }
LOCUST_HOST="${LOCUST_HOST:-http://localhost:8080}"

# run_locust <name> <run-time>  -> results/<name>_stats.csv, results/<name>_headers.json
run_locust() {
  LOADTEST_HEADERS_OUT="results/$1_headers.json" locust -f tools/locustfile.py --headless \
    --users 4 --spawn-rate 4 --run-time "$2" --host "$LOCUST_HOST" --csv "results/$1" \
    > "results/$1_locust.log" 2>&1 || true
  python3 scripts/locust_summary.py "results/$1"
}

wait_ready_replicas() {  # wait_ready_replicas <n>
  for _ in $(seq 1 180); do
    r=$(kubectl -n app get deploy kd-service -o jsonpath='{.status.readyReplicas}')
    [ "${r:-0}" = "$1" ] && return 0; sleep 2
  done; echo "timeout waiting for $1 ready replicas"; return 1
}
