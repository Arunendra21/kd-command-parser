# Knowledge Distillation and Deployment of a Lightweight Command Parser on a Local Cloud

Cloud Computing (CS3081) mini project. **Arunendra Tripathi, 230103016**, IIIT Manipur.

- GitHub repository: https://github.com/Arunendra21/kd-command-parser
- Model releases (weights, tokenizer, version info, checksums): https://github.com/Arunendra21/kd-command-parser/releases
- Report: [`report/report.pdf`](report/report.pdf)

The teacher **phi3.5** (Phi-3.5-mini-instruct, 3.8B, Ollama, temperature 0, seed 42) labels 3,000 commands
with a four-key JSON frame. The student **EleutherAI/pythia-70m** is fine-tuned on the teacher's replies
(sequence-level knowledge distillation). The student is served by a FastAPI service on a single-node k3d
cluster, and the model is loaded from SeaweedFS object storage.

```
             Colab T4 (free)                         k3d cluster "kdcloud" (Codespaces / laptop)
        ┌──────────────────────┐   HTTPS    ┌──────────────────────────────────────────────────────┐
        │ Ollama phi3.5        │◄───────────┤ ns pipeline: Indexed Job, SHARD_COUNT worker pods     │
        │ (cloudflared tunnel) │  OLLAMA_URL│        │ shard-i.jsonl                                │
        └──────────────────────┘            │        ▼                                              │
                                            │ ns data: SeaweedFS (S3) buckets datasets/, models/    │
   make train (CPU) ──► artifacts/v1,v2 ───►│        ▲ model download at start-up                   │
   gh release model-v1/v2                   │ ns app: Deployment kd-service (2 pods, HPA 1..2)      │
                                            │         Service ◄── Traefik Ingress /parse :8080      │
                                            └──────────────────────────────────────────────────────┘
```

## Repository layout

| Path | What |
|---|---|
| `cluster/k3d.yaml` | cluster definition (ports 8080 → Ingress, 8333 → SeaweedFS S3) |
| `k8s/` | namespaces, SeaweedFS (`data`), teacher Job (`pipeline`), Deployment/Service/Ingress/HPA (`app`) |
| `prompts/teacher_prompt.txt` | the teacher prompt |
| `worker/` | `worker.py` (shard worker), `clean.py` (cleaning + checksum), `teacher_eval.py`, Dockerfile |
| `training/` | `config.yaml` (v1), `config_v2.yaml`, `train.py`, `predict.py`, `publish.py`, `loss.csv` |
| `service/` | FastAPI app, shared schema/extraction logic (`core.py`), Dockerfile, pinned `requirements.txt` |
| `network/` | `subnets.md`, `nacl.json`, `packets_sample.jsonl` |
| `tests/` | unit tests (schema validation, cleaning rules, sharding, API, NACL) |
| `.github/workflows/ci.yml` | lint → unit tests → evaluation of the Release model → quality gate; gitleaks |
| `data/`, `tools/` | the student kit, unchanged |
| `results/` | all evidence: logs, score reports, Locust CSVs, command outputs |
| `colab/teacher_ollama.ipynb` | teacher server on a free Colab GPU |

## Prerequisites

Docker, k3d v5, kubectl, Python 3.11, `gh` (only for releases). Opening the repository in **GitHub Codespaces**
(4-core / 16 GB) installs all of them through `.devcontainer/devcontainer.json`.

```bash
pip install -r requirements-dev.txt     # host-side training, evaluation, tests, Locust
```

## Build and deploy (fresh clone, three commands)

```bash
git clone https://github.com/Arunendra21/kd-command-parser.git
cd kd-command-parser
make up
```

`make up` does the following:
1. Creates the cluster from `cluster/k3d.yaml` and the namespaces `data`, `pipeline` and `app`.
2. Generates S3 credentials into `.secrets/` (git-ignored) and loads them as Kubernetes Secrets.
3. Deploys SeaweedFS, creates the buckets `datasets` and `models`, and uploads `commands_pool.jsonl`.
4. Builds both images and imports them into the cluster.
5. Copies model v1 and v2 from the GitHub Release into `s3://models/` after verifying their checksums.
6. Deploys the service.

Test it:

```bash
curl -i -X POST localhost:8080/parse -H 'content-type: application/json' -d '{"text":"set an alarm for seven thirty am tomorrow"}'
```

## Full pipeline (how the results were produced)

```bash
# Task 1: teacher labelling. Start colab/teacher_ollama.ipynb first; it prints OLLAMA_URL.
make label OLLAMA_URL=https://<id>.trycloudflare.com SHARD_COUNT=3
make clean-data                      # -> s3://datasets/v1/train.jsonl + train.sha256, results/clean_counts.json
make teacher-eval OLLAMA_URL=...     # -> results/teacher_validation.json

# Task 2: student
make train SUBSET=50                 # quick check
make train                           # v1 (training/config.yaml) -> artifacts/v1, training/loss.csv
make train-v2                        # v2 (one more epoch)
make publish VERSION=v1 && make publish VERSION=v2      # s3://models/v1|v2 + model.sha256
make release VERSION=v1 && make release VERSION=v2      # GitHub Release assets
make eval-base && make eval-student VERSION=v1

# Tasks 3, 4, 7: evidence (writes into results/)
make task3
make deploy
make task4                           # or PART=resources|coldstart|hpa|lb|rolling|recovery
make task7

# Task 5
python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check

# Task 6
make lint test
```

Standard load test (the same command is used for assessment):

```bash
locust -f tools/locustfile.py --headless --users 4 --spawn-rate 4 --run-time 2m --host http://localhost:8080 --csv results/loadtest
```

## Shut down

```bash
make down          # deletes the k3d cluster (all namespaces, SeaweedFS data)
```

## Notes
- No model weights or credentials are stored in Git or in the image. Models live in SeaweedFS and in GitHub Releases. Credentials are generated per cluster into `.secrets/`, which is git-ignored.
- The teacher ran on a free Colab T4 GPU instead of the laptop, because a CPU could not label 3,000 commands in the time available. Prompt, model and settings are unchanged. See the report, Task 1.
- AI tool usage is documented in [`AI_USE.md`](AI_USE.md).
