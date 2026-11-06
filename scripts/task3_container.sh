#!/usr/bin/env bash
# Task 3 evidence: image size/no weights, endpoints + headers, FAULT_INJECT, 50 requests at 1 CPU / 1 GiB.
set -uo pipefail
source scripts/lib.sh
IMG=kd-service:1.0
ENVS=(-e MODEL_URI=s3://models/v1 -e MODEL_VERSION=v1 -e S3_ENDPOINT=http://host.docker.internal:8333
      -e MAX_NEW_TOKENS=64 --env-file .secrets/s3.env --add-host=host.docker.internal:host-gateway)

say "image size"; docker image ls $IMG --format '{{.Repository}}:{{.Tag}} {{.Size}}'
docker image inspect $IMG --format 'bytes: {{.Size}}'
say "no model weights inside the image (search for *.safetensors / pytorch_model*.bin / model dirs)"
docker run --rm --entrypoint sh $IMG -c "find / \( -name '*.safetensors' -o -name 'pytorch_model*.bin' \) -not -path '/proc/*' 2>/dev/null | wc -l; ls -la /tmp/model"

docker rm -f kd-t3 kd-t3-fault >/dev/null 2>&1
say "start container with --cpus=1 --memory=1g --memory-swap=1g"
docker run -d --name kd-t3 --cpus=1 --memory=1g --memory-swap=1g -p 8000:8000 -e FAULT_INJECT=0 "${ENVS[@]}" $IMG
( while docker inspect kd-t3 >/dev/null 2>&1; do
    docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' kd-t3 | sed "s/^/$(ts) /"; sleep 1
  done ) > results/task3_docker_stats.txt 2>/dev/null &
STATS=$!
say "/healthz and /readyz while loading"
curl -s -o /dev/null -w 'healthz %{http_code}\n' localhost:8000/healthz || true
for i in $(seq 1 120); do
  c=$(curl -s -o /dev/null -w '%{http_code}' localhost:8000/readyz); echo "$(ts) readyz $c"
  [ "$c" = 200 ] && break; sleep 1
done
say "headers"; curl -si localhost:8000/healthz; echo; curl -si localhost:8000/readyz; echo
curl -si -X POST localhost:8000/parse -H 'content-type: application/json' -d '{"text":"set an alarm for seven thirty am tomorrow"}'; echo

say "50 sequential requests"
python3 - <<'PY'
import json, time, urllib.request, collections
texts = [json.loads(l)["text"] for l in open("data/validation.jsonl")][:50]
codes, lat = collections.Counter(), []
for t in texts:
    req = urllib.request.Request("http://localhost:8000/parse", data=json.dumps({"text": t}).encode(),
                                 headers={"content-type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r: codes[r.status] += 1
    except urllib.error.HTTPError as e: codes[e.code] += 1
    lat.append(time.time() - t0)
lat.sort()
print("status codes:", dict(codes), " median latency %.0f ms, max %.0f ms" % (1000 * lat[len(lat)//2], 1000 * lat[-1]))
PY
say "peak memory (cgroup memory.peak / max_usage) and OOM status"
docker exec kd-t3 sh -c 'cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes' \
  | awk '{printf "peak bytes: %d (%.1f MiB)\n", $1, $1/1048576}'
docker inspect kd-t3 --format 'OOMKilled={{.State.OOMKilled}} Status={{.State.Status}} RestartCount={{.RestartCount}}'
kill $STATS 2>/dev/null
echo "highest docker stats sample:"; sort -k4 -h results/task3_docker_stats.txt | tail -1
docker logs kd-t3 > results/task3_container_stdout.log 2>&1

say "FAULT_INJECT=1"
docker run -d --name kd-t3-fault --cpus=1 --memory=1g -p 8001:8000 -e FAULT_INJECT=1 "${ENVS[@]}" $IMG
for i in $(seq 1 120); do [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:8001/readyz)" = 200 ] && break; sleep 1; done
curl -si -X POST localhost:8001/parse -H 'content-type: application/json' -d '{"text":"what is the weather in london"}'; echo
docker rm -f kd-t3 kd-t3-fault >/dev/null
