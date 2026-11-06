# Knowledge distillation + local-cloud deployment of a command parser.
# Fresh clone:  git clone https://github.com/Arunendra21/kd-command-parser && cd kd-command-parser && make up
SHELL := /bin/bash
.ONESHELL:
.SHELLFLAGS := -eu -o pipefail -c

CLUSTER      ?= kdcloud
K3D_CONFIG   ?= cluster/k3d.yaml
GITHUB_REPO  ?= Arunendra21/kd-command-parser
SHARD_COUNT  ?= 3
OLLAMA_URL   ?=
SUBSET       ?=
VERSION      ?= v1
PART         ?= all
PY           ?= python3
S3ENV         = set -a && . ./.secrets/s3.env && set +a && export S3_ENDPOINT=http://localhost:8333

.PHONY: up down cluster storage secrets images deploy seed-models label clean-data teacher-eval \
        train train-v2 publish release eval-base eval-student scores test lint loadtest \
        task3 task4 task7 status help

help:
	@grep -E '^[a-z0-9-]+:.*?## ' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

# ---------------------------------------------------------------- whole system
up: cluster secrets storage images seed-models deploy ## build and deploy everything (cluster, SeaweedFS, images, models, app)
	@echo "Ready: curl -s -X POST localhost:8080/parse -H 'content-type: application/json' -d '{\"text\":\"wake me up at seven am\"}'"

down: ## delete the cluster
	k3d cluster delete $(CLUSTER)

cluster: ## create the k3d cluster from cluster/k3d.yaml
	k3d cluster list $(CLUSTER) >/dev/null 2>&1 || k3d cluster create --config $(K3D_CONFIG)
	kubectl apply -f k8s/namespaces.yaml
	kubectl -n kube-system rollout status deploy/metrics-server --timeout=180s

secrets: ## generate S3 credentials (git-ignored) and load them as Secrets
	./scripts/secrets.sh

images: ## build the worker and service images and import them into the cluster
	docker build -f worker/Dockerfile -t kd-worker:1.0 .
	docker build -f service/Dockerfile -t kd-service:1.0 .
	docker image ls kd-service:1.0 --format '{{.Repository}}:{{.Tag}} {{.Size}}' | tee results/image_size.txt
	k3d image import -c $(CLUSTER) kd-worker:1.0 kd-service:1.0

storage: ## deploy SeaweedFS in namespace data, create buckets, upload the dataset
	kubectl apply -f k8s/data/seaweedfs.yaml
	kubectl -n data rollout status deploy/seaweedfs --timeout=300s
	docker image inspect kd-worker:1.0 >/dev/null 2>&1 || docker build -f worker/Dockerfile -t kd-worker:1.0 .
	docker run --rm --network host --env-file .secrets/s3.env -e S3_ENDPOINT=http://localhost:8333 \
	  -v "$$PWD":/repo kd-worker:1.0 python /repo/scripts/s3_init.py | tee results/storage_init.log

seed-models: ## make sure s3://models/v1 and v2 exist (from artifacts/ or the GitHub Release)
	GITHUB_REPO=$(GITHUB_REPO) ./scripts/seed_models.sh

deploy: ## deploy the service (Deployment, Service, Ingress, HPA) in namespace app
	kubectl apply -f k8s/app/
	kubectl -n app rollout status deploy/kd-service --timeout=600s

status:
	kubectl get pods,svc,ingress,hpa -A -o wide | grep -E 'NAMESPACE|data|pipeline|app'

# ---------------------------------------------------------------- Task 1: teacher labelling
label: ## run SHARD_COUNT teacher workers in namespace pipeline (needs OLLAMA_URL)
	test -n "$(OLLAMA_URL)" || { echo "set OLLAMA_URL=https://...  (see colab/teacher_ollama.ipynb)"; exit 1; }
	kubectl -n pipeline create configmap teacher-prompt --from-file=prompts/teacher_prompt.txt \
	  --dry-run=client -o yaml | kubectl apply -f -
	kubectl -n pipeline delete job teacher-label --ignore-not-found
	sed -e 's#__SHARD_COUNT__#$(SHARD_COUNT)#g' -e 's#__OLLAMA_URL__#$(OLLAMA_URL)#g' \
	  k8s/pipeline/teacher-job.yaml | kubectl apply -f -
	sleep 5; kubectl -n pipeline get pods -o wide | tee results/pipeline_pods.txt
	for i in $$(seq 1 2160); do  # up to 6 h; stop early if the Job fails
	  s=$$(kubectl -n pipeline get job teacher-label -o jsonpath='{.status.succeeded}')
	  f=$$(kubectl -n pipeline get job teacher-label -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}')
	  [ "$${s:-0}" = "$(SHARD_COUNT)" ] && break
	  [ "$$f" = True ] && { echo "teacher-label Job failed"; kubectl -n pipeline describe job teacher-label | tail; exit 1; }
	  sleep 10
	done
	kubectl -n pipeline get pods -o wide | tee -a results/pipeline_pods.txt
	for p in $$(kubectl -n pipeline get pods -l app=teacher-worker -o name); do
	  kubectl -n pipeline logs $$p > results/worker_$${p#pod/}.log; done
	( $(S3ENV) && cd worker && $(PY) -c "import s3util, os; s=s3util.client(); \
	  os.makedirs('../results/teacher_shards', exist_ok=True); \
	  [s.download_file('datasets', k, '../results/teacher_shards/' + k.split('/')[-1]) for k in s3util.list_keys(s, 'datasets', 'teacher/shard-')]" )
	$(PY) scripts/check_shards.py results/teacher_shards data/commands_pool.jsonl | tee results/shard_check.txt

clean-data: ## clean shard outputs -> s3://datasets/v1/train.jsonl + train.sha256
	$(S3ENV) && $(PY) worker/clean.py | tee results/clean.log

teacher-eval: ## teacher on validation.jsonl (same prompt/settings) -> results/teacher_validation.json
	test -n "$(OLLAMA_URL)"
	OLLAMA_URL=$(OLLAMA_URL) $(PY) worker/teacher_eval.py --out results/teacher_validation_predictions.jsonl
	$(PY) tools/score.py results/teacher_validation_predictions.jsonl data/validation.jsonl \
	  --out results/teacher_validation.json

# ---------------------------------------------------------------- Task 2: student
train: ## train the student from training/config.yaml (SUBSET=50 for a quick check)
	$(PY) training/train.py --config training/config.yaml $(if $(SUBSET),--subset $(SUBSET),) 2>&1 \
	  | tee results/train_$(if $(SUBSET),subset$(SUBSET),v1).log

train-v2: ## train model v2 from training/config_v2.yaml
	$(PY) training/train.py --config training/config_v2.yaml 2>&1 | tee results/train_v2.log

publish: ## checksum artifacts/$(VERSION) and upload to s3://models/$(VERSION)/
	$(S3ENV) && $(PY) training/publish.py --version $(VERSION) | tee results/publish_$(VERSION).log

release: ## publish artifacts/$(VERSION) as GitHub Release model-$(VERSION)
	cd artifacts/$(VERSION) && gh release create model-$(VERSION) --repo $(GITHUB_REPO) \
	  --title "Student model $(VERSION)" --notes-file version.json $$(awk '{print $$2}' model.sha256) model.sha256

eval-base: ## untrained Pythia-70M on validation
	$(PY) training/predict.py --model EleutherAI/pythia-70m --out results/base_validation_predictions.jsonl
	$(PY) tools/score.py results/base_validation_predictions.jsonl data/validation.jsonl --out results/base_validation.json

eval-student: ## trained student artifacts/$(VERSION) on validation
	$(PY) training/predict.py --model artifacts/$(VERSION) --out results/student_$(VERSION)_validation_predictions.jsonl
	$(PY) tools/score.py results/student_$(VERSION)_validation_predictions.jsonl data/validation.jsonl \
	  --out results/student_$(VERSION)_validation.json

# ---------------------------------------------------------------- tests / evidence
lint:
	ruff check .

test: ## unit tests
	$(PY) -m pytest -q tests

task3: ## container test: endpoints, FAULT_INJECT, 50 requests at 1 CPU / 1 GiB
	./scripts/task3_container.sh 2>&1 | tee results/task3_container.log

task4: ## Kubernetes tests (PART=all|resources|coldstart|hpa|lb|rolling|recovery|restore)
	./scripts/task4_k8s.sh $(PART) 2>&1 | tee results/task4_$(PART).log

task7: ## standard load test + kubectl top
	./scripts/task7_perf.sh 2>&1 | tee results/task7_perf.log
