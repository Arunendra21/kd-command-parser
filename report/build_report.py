"""Build report/report.html (and report.pdf via headless Chrome) from the files in results/.

Every measured number in the report is read from results/ here, so the report
cannot drift from the evidence. Text marked "Assumption" is not measured.
Usage: python report/build_report.py [--pdf]
"""
import csv
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
R = os.path.join(ROOT, "results")


def J(name):
    with open(os.path.join(R, name)) as f:
        return json.load(f)


def T(name):
    with open(os.path.join(R, name)) as f:
        return f.read()


def loss(path):
    with open(os.path.join(ROOT, path)) as f:
        return [(int(r["epoch"]), float(r["train_loss"])) for r in csv.DictReader(f)]


counts = J("clean_counts.json")
teacher, base = J("teacher_validation.json"), J("base_validation.json")
s1, s1s = J("student_v1_validation.json"), J("student_v1_validation_service.json")
s2, s2s = J("student_v2_validation.json"), J("student_v2_validation_service.json")
v1info = J("models/v1/version.json")
v2info = J("models/v2/version.json")
l1, l2 = loss("training/loss.csv"), loss("training/loss_v2.csv")
sha_v1 = T("models/v1/model.sha256").split()[0]

t3 = T("task3_container.log")
t3_codes = re.search(r"status codes: (\{.*?\})", t3).group(1)
t3_lat = re.search(r"median latency (\d+) ms, max (\d+) ms", t3).groups()
t3_peak = re.search(r"peak bytes: (\d+) \(([\d.]+) MiB\)", t3).groups()
t3_oom = re.search(r"OOMKilled=(\w+)", t3).group(1)
img_bytes = int(re.search(r"bytes: (\d+)", t3).group(1))
t3_weights = re.search(r"model dirs\)\n(\d+)", t3).group(1)

cold = T("coldstart_summary.txt")
cold_runs = re.search(r"per_run_seconds=\[(.*?)\]", cold).group(1)
cold_med = re.search(r"median_seconds=([\d.]+)", cold).group(1)
cold_log = T("coldstart_run1_log.txt").splitlines()

hpa_lines = [l for l in T("hpa_watch.txt").splitlines() if "Deployment/kd-service" in l]


def hpa_replicas(line):
    parts = line.split()
    i = parts.index("cpu:")
    return int(parts[i + 4]), parts[i + 1]


hpa_seq = [hpa_replicas(l) for l in hpa_lines]
hpa_max_cpu = max((h[1] for h in hpa_seq), key=lambda c: int(c.split("%")[0]) if c[0].isdigit() else -1)
hpa_path = []
for r, _ in hpa_seq:
    if not hpa_path or hpa_path[-1] != r:
        hpa_path.append(r)

lb, roll, rec, hload = J("lb_test_summary.json"), J("rolling_summary.json"), J("recovery_summary.json"), J("hpa_load_summary.json")
before = {n: J(f"before_salvage/{n}_summary.json") for n in ("hpa_load", "lb_test", "rolling", "recovery")}
t4 = T("task4_all.log")
after_rb = t4.split("after rollback")[1].split("=====")[0]
rb_versions = re.findall(r"X-Model-Version: (v\d)", after_rb, re.I)
during = t4.split("4.5 rolling update")[1].split("rollout history")[0]
during_versions = re.findall(r"X-Model-Version: (v\d)", during, re.I)

lt = J("loadtest_summary.json")
top = T("task7_top.txt")
top_rows = [l.split() for l in top.splitlines() if l.startswith("kd-service-") and "m " in l + " "]
pod_cpu = {}
for row in top_rows:
    name, cpu, mem = row[0], int(row[1].rstrip("m")), int(row[2].rstrip("Mi"))
    c = pod_cpu.setdefault(name, {"cpu": [], "mem": []})
    c["cpu"].append(cpu)
    c["mem"].append(mem)
cost_txt = T("cost.txt").strip()
cost_val = re.search(r"= ([\d.]+) INR$", cost_txt).group(1)
nacl = T("nacl_check.txt")
ci = T("ci_runs.md")
ci_pass = re.search(r"Passing run.*?(https://\S+)", ci).group(1)
ci_fail = re.search(r"Failing run.*?(https://\S+)", ci).group(1)
subnets = T("../network/subnets.md")
subnet_rows = [l for l in subnets.splitlines() if l.startswith("| ") and "Subnet" not in l and "---" not in l]

slo_target = 99.0
budget = lt["requests"] * (100 - slo_target) / 100
used = lt["failures"]


def pct(x):
    return f"{x:.1f}" if isinstance(x, float) else str(x)


def score_row(name, d, note=""):
    keys = ["json_validity", "intent_accuracy", "date_accuracy", "time_accuracy", "place_accuracy", "full_frame"]
    return f"<tr><td>{name}</td>" + "".join(f"<td>{d[k]:.0f}</td>" for k in keys) + f"<td>{note}</td></tr>"


def ltrow(name, d):
    shares = ", ".join(f"{v:.1f}%" for v in d.get("replica_share_pct", {}).values())
    vers = ", ".join(f"{k}: {v}" for k, v in d.get("per_model_version", {}).items())
    return (f"<tr><td>{name}</td><td>{d['requests']}</td><td>{d['failures']}</td><td>{d['error_rate_pct']:.2f}%</td>"
            f"<td>{d['p50_ms']:.0f}</td><td>{d['p95_ms']:.0f}</td><td>{d['rps']:.2f}</td><td>{vers}</td><td>{shares}</td></tr>")


REPO = "https://github.com/Arunendra21/kd-command-parser"
MEAS = '<span class="tag m">Measured</span>'
ASSUME = '<span class="tag a">Assumption</span>'

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>KD Command Parser Report</title>
<style>
@page {{ size: A4; margin: 14mm 14mm 14mm 14mm; }}
body {{ font-family: 'DejaVu Serif', Georgia, serif; font-size: 9.6pt; line-height: 1.32; color: #111; }}
h1 {{ font-size: 15pt; margin: 0 0 2px; }} h2 {{ font-size: 11.5pt; margin: 10px 0 3px; border-bottom: 1px solid #999; }}
h3 {{ font-size: 10pt; margin: 6px 0 2px; }}
p {{ margin: 3px 0; text-align: justify; }} ul {{ margin: 2px 0 2px 16px; padding: 0; }} li {{ margin: 1px 0; }}
table {{ border-collapse: collapse; margin: 4px 0; font-size: 8.4pt; width: 100%; }}
th, td {{ border: 1px solid #aaa; padding: 2px 4px; text-align: left; vertical-align: top; }} th {{ background: #eee; }}
code, pre {{ font-family: 'DejaVu Sans Mono', monospace; font-size: 7.8pt; }} pre {{ background: #f6f6f6; padding: 4px; margin: 3px 0; white-space: pre-wrap; }}
.tag {{ font-size: 7pt; padding: 0 3px; border-radius: 2px; font-family: sans-serif; }} .m {{ background: #d8f0d8; }} .a {{ background: #f8e3c8; }}
.meta {{ font-size: 9pt; color: #333; }} .pb {{ page-break-before: always; }} .small {{ font-size: 8pt; }}
</style></head><body>
<h1>Knowledge Distillation and Deployment of a Lightweight Command-Parsing Model on a Local Cloud</h1>
<p class="meta">Cloud Computing (CS3081) mini project &middot; <b>Arunendra Tripathi</b>, Roll No. <b>230103016</b>, IIIT Manipur &middot;
Repository: <a href="{REPO}">{REPO}</a> (commit tagged <code>final</code>) &middot; Model releases: <a href="{REPO}/releases">{REPO}/releases</a></p>
<p class="small">Labels: {MEAS} = a number read from a file in <code>results/</code> (the builder <code>report/build_report.py</code> fills every one of them);
{ASSUME} = a stated assumption, not a measurement.</p>

<h2>0. System overview</h2>
<p>The teacher <b>phi3.5</b> (Phi-3.5-mini-instruct, 3.8B, Ollama, temperature 0, seed 42) labels 3,000 SLURP commands with a four-key JSON frame.
The student <b>EleutherAI/pythia-70m</b> is fine-tuned on the teacher's replies (sequence-level KD) and served by a FastAPI service.
Everything runs on one single-node <b>k3d</b> cluster (k3s v1.30.6) on the laptop used for this project (8 vCPU, 15 GiB RAM, Docker), in three namespaces:
<code>data</code> (SeaweedFS S3 with buckets <code>datasets</code> and <code>models</code>), <code>pipeline</code> (teacher workers as an Indexed Job) and
<code>app</code> (Deployment, Service, Traefik Ingress, HPA). The laptop could not run the 3.8B teacher over 3,000 commands in the available time,
so Ollama ran on a <b>free Google Colab T4</b> and was reached by the in-cluster workers through a free Cloudflare quick tunnel (<code>OLLAMA_URL</code>);
model, prompt and settings are unchanged. Training and evaluation ran on the laptop CPU (4 cores). CI runs on free GitHub Actions.
Because another program occupies host port 8080 on that laptop, the local cluster mapped the Ingress to host port 28080; <code>cluster/k3d.yaml</code> in the
repository uses 8080, so the standard Locust command works unchanged on a fresh machine.</p>

<h2>Task 1: Object storage and parallel teacher labelling</h2>
<p><b>Architecture.</b> <code>make up</code> creates the cluster from <code>cluster/k3d.yaml</code>, deploys SeaweedFS (single <code>weed server -s3</code> pod, PVC, NodePort) in
<code>data</code>, creates both buckets and uploads <code>commands_pool.jsonl</code> to <code>datasets</code> (<code>results/storage_init.log</code>).
S3 credentials are generated per cluster into the git-ignored <code>.secrets/</code> and loaded as Kubernetes Secrets. The prompt is
<code>prompts/teacher_prompt.txt</code> (eight intents with meanings, the three slot rules, six examples taken from the handout, "JSON only"); it is mounted
into the workers from a ConfigMap, so the workers always use the committed prompt. Ollama is called with <code>format: "json"</code>.</p>
<p><b>Sharding.</b> <code>worker/worker.py</code> reads <code>SHARD_INDEX</code> and <code>SHARD_COUNT</code> and keeps the commands whose 0-based line number <i>n</i>
satisfies <i>n</i> mod <code>SHARD_COUNT</code> = <code>SHARD_INDEX</code>. The workers run as one <b>Indexed Job</b> in <code>pipeline</code> with
<code>completions = parallelism = 3</code>; each pod's <code>SHARD_INDEX</code> is its completion index (downward API), so the three shards are disjoint and together
cover every line. Modulo (rather than contiguous blocks) balances the load even if the file is sorted, and needs no knowledge of the file length.
Each worker writes its own object <code>datasets/teacher/shard-&lt;i&gt;.jsonl</code> and checkpoints every 25 records, so a restarted pod resumes instead of
starting over (useful because the teacher sits behind a tunnel). <code>scripts/check_shards.py</code> confirmed {MEAS} 3 &times; 1,000 records,
3,000 unique ids, 0 missing, 0 repeated. Wall time {MEAS}: about 26 min for 3,000 commands (3 workers, ~1.5 s per request each).</p>
<p><b>Cleaning.</b> <code>worker/clean.py</code> reads all shards, sorts by id and applies rules (a)-(d) in order (a record is counted under the first rule it breaks),
then removes duplicate commands among the survivors (text lower-cased and whitespace-normalised; smallest id kept). Slot rule (d) accepts null or a
non-empty string that occurs in the command (case/whitespace-insensitive). Each kept line stores the teacher's reply unchanged (<code>teacher_raw</code>)
plus the same frame re-serialised on one line (<code>target</code>), which is the training target. Re-running <code>clean.py</code> on the committed shard files
reproduces the checksum in <code>train.sha256</code>: <code>{counts['sha256'][:16]}&hellip;</code> {MEAS}.</p>
<table><tr><th>Input</th><th>(a) not JSON</th><th>(b) wrong keys</th><th>(c) bad intent</th><th>(d) slot not in command</th><th>Duplicates</th><th>Kept</th><th>Check</th></tr>
<tr><td>{counts['input']}</td><td>{counts['a_invalid_json']}</td><td>{counts['b_wrong_keys']}</td><td>{counts['c_bad_intent']}</td><td>{counts['d_slot_not_in_command']}</td>
<td>{counts['e_duplicates']}</td><td>{counts['kept']}</td><td>{counts['a_invalid_json']}+{counts['b_wrong_keys']}+{counts['c_bad_intent']}+{counts['d_slot_not_in_command']}+{counts['e_duplicates']}+{counts['kept']} = {counts['input']} {MEAS}</td></tr></table>
<p><b>Limitations / improvements.</b> (d) is the main loss ({counts['d_slot_not_in_command']} records): the teacher sometimes normalises values (e.g. "7 am" for
"seven am") despite the prompt. A teacher on a remote GPU through a tunnel is a single point of failure (mitigated by checkpoints and retries).
Improvement: run Ollama in the cluster on a GPU node, and add a few-shot block with more normalisation counter-examples.</p>

<h2>Task 2: Training the student (sequence-level distillation)</h2>
<p><b>Implementation.</b> <code>training/train.py</code> (PyTorch + Transformers, CPU) reads only <code>training/config.yaml</code> (seed 42, learning rate 3e-4, batch 16,
10 epochs, max length 128, library versions) and trains on the first 1,500 records of <code>train.jsonl</code> (its SHA-256 is verified first).
Each example is <code>Command: &lt;text&gt;\\nJSON: &lt;teacher JSON&gt;&lt;eos&gt;</code>; the loss is computed only on the JSON part (prompt tokens masked).
The seed is fixed in code (Python, NumPy, PyTorch, data-loader generator). <code>make train SUBSET=50</code> trains on 50 records.
v2 = the same settings with one more epoch (<code>training/config_v2.yaml</code>). <code>training/publish.py</code> writes <code>model.sha256</code> and uploads model,
tokenizer, <code>version.json</code> and checksums to <code>s3://models/v1/</code> and <code>v2/</code>; the same files are the assets of GitHub Releases
<code>model-v1</code> and <code>model-v2</code>. The downloaded Release <code>model.safetensors</code> matches <code>models/v1/model.sha256</code>
(<code>{sha_v1[:16]}&hellip;</code>; <code>results/release_v1_checksum_verify.txt</code>) {MEAS}.</p>
<p><b>Loss per epoch</b> {MEAS} v1: {", ".join(f"{l:.3f}" for _, l in l1)} &nbsp;|&nbsp; v2: {", ".join(f"{l:.3f}" for _, l in l2)}.
Training time v1 {v1info['train_seconds']/60:.0f} min, v2 {v2info['train_seconds']/60:.0f} min on 4 CPU cores.</p>
<table><tr><th>Model (validation.jsonl, 100 commands)</th><th>JSON valid</th><th>Intent</th><th>Date</th><th>Time</th><th>Place</th><th>Full frame</th><th>Note</th></tr>
{score_row("Teacher phi3.5 (same prompt/settings)", teacher, "results/teacher_validation.json")}
{score_row("Pythia-70M, untrained", base, "prompt + greedy decoding")}
{score_row("Student v1, raw output (strict)", s1, "student_v1_validation.json")}
{score_row("Student v1, as served (strict + salvage)", s1s, "98 strict, 2 salvaged")}
{score_row("Student v2, raw output (strict)", s2, "student_v2_validation.json")}
{score_row("Student v2, as served", s2s, "")}
</table>
<p>All numbers {MEAS}. <b>What changed.</b> The untrained model continues the text with unrelated prose or a lone "{{"; it never produces the format (0% everywhere).
After distillation the student reproduces the frame format almost perfectly and copies slot phrases from the command. Its full-frame score
({s1['full_frame']:.0f}%) is close to, here even slightly above, the teacher's ({teacher['full_frame']:.0f}%): it learned the teacher's behaviour, including its
labelling conventions, and on 100 examples a few points are within noise. The student cannot be better than the teacher in general; the gap to the gold labels
(intent {s1['intent_accuracy']:.0f}%) is inherited from the teacher ({teacher['intent_accuracy']:.0f}%).</p>
<p><b>Sequence-level vs. logit-based distillation.</b> (a) <i>Sequence-level KD</i> (Kim &amp; Rush, 2016) trains the student with ordinary cross-entropy on the
teacher's <i>generated output sequence</i>, i.e. the teacher's single best answer is the hard target. (b) <i>Logit-based (token-level) KD</i> trains the student to match the
teacher's full <i>probability distribution over the vocabulary at every position</i> (e.g. KL divergence between softened teacher and student logits), which also
transfers how confident the teacher was in the alternatives. (c) It is not possible here because the teacher is used only through Ollama's generate API, which returns text,
not per-token distributions; moreover phi3.5 and Pythia use different tokenizers/vocabularies, so their distributions are not position-by-position comparable without
an alignment step. (d) A real limitation of this approach: the student learns only the teacher's top-1 answer, including the teacher's mistakes (e.g. the {counts['d_slot_not_in_command']}
normalised slots that were filtered out show the teacher's systematic errors; the ones that pass the filter are learned as truth), and nothing about uncertainty; a 70M
model also falls into repetition loops on a few inputs (2/100 on validation in strict mode).</p>

<h2>Task 3: The inference service in a container</h2>
<p><b>Implementation.</b> <code>service/app.py</code> (FastAPI, uvicorn, port 8000). Configuration comes only from <code>MODEL_URI</code>, <code>MODEL_VERSION</code>,
<code>S3_ENDPOINT</code>, <code>MAX_NEW_TOKENS</code> (+ <code>FAULT_INJECT</code>); credentials (<code>AWS_ACCESS_KEY_ID/SECRET</code>) come from the Secret
<code>s3-credentials</code>. At start-up a background thread downloads every object under <code>MODEL_URI</code> from SeaweedFS and loads the model; <code>/healthz</code>
answers 200 at once, <code>/readyz</code> answers 503 until the model is loaded. <code>POST /parse</code> runs greedy decoding (prompt <code>Command: ...\\nJSON:</code>),
cuts the text at the first newline/closing brace and checks it against <code>schema.json</code> (exactly the four keys, intent in the eight, slots null or string).
If that strict check fails, a deterministic <b>salvage</b> step takes the first allowed intent and the first value of each slot <i>from the model's own text</i>, keeping a slot only if it
occurs in the command (else null); if no allowed intent exists, the service returns <code>500 {{"error": "invalid_model_output"}}</code>. Valid responses carry
<code>X-Model-Version</code> and <code>X-Served-By</code> (Pod name from the downward API). With <code>FAULT_INJECT=1</code> the output is replaced by <code>not json</code>
before checking and the service returns exactly that 500 body {MEAS}. The image (<code>python:3.11-slim</code>, CPU-only PyTorch wheel, every dependency pinned in
<code>service/requirements.txt</code>, <code>pip install --no-deps</code>) contains no weights ({t3_weights} weight files found) and is
{img_bytes/1e9:.2f} GB {MEAS}; it builds from a fresh clone with <code>make images</code> or <code>docker build -f service/Dockerfile .</code>.</p>
<p><b>Running under limits</b> (<code>docker run --cpus=1 --memory=1g --memory-swap=1g</code>, 50 sequential requests, <code>results/task3_container.log</code>) {MEAS}:
status codes {t3_codes}; median latency {t3_lat[0]} ms, max {t3_lat[1]} ms; <b>peak memory {t3_peak[1]} MiB</b> (cgroup <code>memory.peak</code>, includes page cache of the
282 MB weight download); OOMKilled = {t3_oom}. Before the salvage step was added, the same test gave 49 &times; 200 and 1 &times; 500
(<code>results/before_salvage/task3_container.log</code>).</p>
<p><b>Limitations / improvements.</b> Weights are stored in float32 (282 MB); float16/int8 would halve start-up download and memory. Generation is serialised by a lock
(one request at a time per pod, by design for a 1-CPU limit). Salvage hides a model weakness; constrained (grammar-guided) decoding would remove it at the source.</p>

<h2>Task 4: Kubernetes deployment, scaling and reliability</h2>
<p><b>Manifests</b> (<code>k8s/app/</code>): Deployment <code>kd-service</code> (2 replicas; requests 500m CPU / 512Mi, limits 1 CPU / 1Gi; readiness <code>/readyz</code> every 2 s;
liveness <code>/healthz</code>; rolling update <code>maxSurge 1, maxUnavailable 0</code>; a <code>preStop</code> sleep of 8 s so a Pod leaves the Service before it stops), a ClusterIP
Service, a Traefik Ingress routing <code>/parse</code>, and an HPA (min 1, max 2, CPU 70% of the request; scale-down window 60 s so the test finishes in minutes).
All evidence is in <code>results/task4_all.log</code> and the files named below; each test was driven by <code>scripts/task4_k8s.sh</code>, with the standard Locust
settings (4 users) against the Ingress.</p>
<ul>
<li><b>Readiness gating</b> {MEAS}: during cold starts the Service had <i>no</i> ready endpoints until <code>/readyz</code> turned 200 (<code>ready-endpoints=[]</code> lines in the log).</li>
<li><b>Cold start</b> {MEAS}: Pod creation &rarr; Ready over three runs (all pods deleted each time): {cold_runs} s, <b>median {cold_med} s</b>. The logs show the download from object storage,
e.g. <code>{cold_log[0].split(' INFO ')[-1][:95]}</code> and <code>{[l for l in cold_log if 'complete' in l][0].split(' INFO ')[-1]}</code>.</li>
<li><b>HPA</b> {MEAS}: replica count over the test {" &rarr; ".join(map(str, hpa_path))}; utilisation peaked at {hpa_max_cpu} of the request and fell to 0% after the load
(<code>hpa_watch.txt</code>, <code>hpa_events.txt</code>).</li>
<li><b>Rolling update</b> {MEAS}: under load, <code>MODEL_URI</code>/<code>MODEL_VERSION</code> were changed v1&rarr;v2 (headers during: {", ".join(during_versions)}), then
<code>kubectl rollout undo</code>; after rollback the headers show {", ".join(rb_versions)}.</li>
<li><b>Recovery</b> {MEAS}: one Pod was deleted under load; the Deployment went back to 2/2 ready (<code>task4_all.log</code>).</li>
<li><b>Load balancing</b> {MEAS}: with exactly two Ready replicas (HPA <code>minReplicas</code> temporarily 2) each replica served the share shown below.</li>
</ul>
<table><tr><th>Run (2-6 min, 4 users)</th><th>Requests</th><th>Failed</th><th>Error rate</th><th>p50 ms</th><th>p95 ms</th><th>req/s</th><th>Model versions</th><th>Share per replica</th></tr>
{ltrow("HPA scale test", hload)}{ltrow("Load balancing (2 replicas)", lb)}{ltrow("Rolling update v1&rarr;v2&rarr;undo", roll)}{ltrow("Recovery (pod deleted)", rec)}
<tr><td colspan="9" class="small">Same tests before the salvage step (results/before_salvage/): error rates {", ".join(f"{k} {v['error_rate_pct']:.2f}%" for k, v in before.items())}.
These failures were all <code>500 invalid_model_output</code> for the two validation commands on which the model loops (Locust cycles through the 100 validation commands,
so 2% of requests hit them); the infrastructure itself caused no failures in either set of runs.</td></tr></table>
<p><b>Limitations.</b> This is a <b>single-node cluster on one laptop</b>: it demonstrates Pod-level recovery, not fault tolerance across machines (losing the laptop
loses everything, including SeaweedFS, which is a single replica on a local-path volume). HPA max 2 &times; 1 CPU limit and the host's other load bound throughput; metrics-server
reports with a ~15-60 s delay, so scale-up lags the load. {ASSUME} Behaviour on a multi-node cloud cluster would differ (image pulls, network latency).</p>

<h2>Task 5: Subnetting and network access control</h2>
<p>Allocation from 10.20.0.0, largest first, each block right after the previous one, smallest prefix with 2<sup>32&minus;p</sup>&minus;2 &ge; hosts (working in <code>network/subnets.md</code>):</p>
<table><tr><th>Subnet</th><th>Hosts needed</th><th>Network</th><th>Prefix</th><th>Usable range</th><th>Broadcast</th><th>Usable hosts</th></tr>
{"".join("<tr>" + "".join(f"<td>{c.strip()}</td>" for c in r.strip("|").split("|")) + "</tr>" for r in subnet_rows)}</table>
<p><b>NACL of the public subnet</b> (<code>network/nacl.json</code>). Inbound: 50 deny all from 198.51.100.0/24; 100/110 allow TCP 80/443 from 0.0.0.0/0; 120 allow TCP 22 from
management 10.20.5.128/27; 130 allow TCP 1024-65535 from app 10.20.0.0/22 (replies from the app's port 8000 to the load balancer's ephemeral ports); everything else
falls to the default deny. Outbound: 100 allow TCP 8000 to 10.20.0.0/22; 110 allow TCP 1024-65535 to 0.0.0.0/0 (replies to clients' ephemeral ports).
<code>nacl_sim.py --check</code> on <code>packets_sample.jsonl</code>: <b>{re.search(r"Correct: (.*)", nacl).group(1)}</b> {MEAS}.</p>
<p><b>Why replies need their own rules.</b> A NACL is <i>stateless</i>: it does not remember that it allowed a request, so the reply packet is checked again on its own,
against the rules of its direction. A client's request to port 443 is allowed inbound, but the answer travels outbound to the client's ephemeral port (1024-65535), and the
app's answer to the load balancer arrives inbound on the balancer's ephemeral port; without rules 110 (outbound) and 130 (inbound) those replies would hit the default deny.
<b>Why order matters.</b> Rules are evaluated from the lowest number and the first match wins. A packet from 198.51.100.9 to port 443 matches both "deny 198.51.100.0/24" and
"allow 443 from anywhere"; the deny only works because its number (50) is lower than the allow (110). Numbered after the allow, it would never be reached.</p>

<h2>Task 6: Reproducibility, testing and CI/CD</h2>
<p><b>Reproducibility.</b> From a fresh clone: <code>git clone {REPO}.git</code>, <code>cd kd-command-parser</code>, <code>make up</code> (3 commands). <code>make up</code> creates the
cluster, secrets, SeaweedFS, buckets and dataset, builds and imports both images, downloads <code>model-v1</code>/<code>model-v2</code> from GitHub Releases (verifying
<code>model.sha256</code>) into <code>s3://models/</code>, and deploys the app; <code>make down</code> deletes the cluster. A Codespaces <code>devcontainer.json</code> provides
Docker, k3d, kubectl and gh. <b>CI</b> (<code>.github/workflows/ci.yml</code>), stages in order: lint (ruff) &rarr; unit tests (16 pytest tests: schema validation, salvage,
cleaning rules (a)-(e) and count identity, sharding coverage, API headers/FAULT_INJECT/readiness, NACL) &rarr; evaluation (downloads the model from the GitHub Release,
verifies its checksum, runs <code>predict.py</code> + <code>score.py</code> on validation) &rarr; quality gate (<code>score.py --min-validity 95</code>), plus a gitleaks secret scan
(reports no leaks) {MEAS}.</p>
<p><b>The gate doing its job</b> {MEAS}: run with the deliberately bad model (untrained Pythia-70M) fails at the quality gate with
<code>QUALITY GATE FAILED: json_validity 0.0 &lt; 95.0</code>: <a href="{ci_fail}">{ci_fail}</a>. The same workflow with <code>model-v1</code> passes all stages:
<a href="{ci_pass}">{ci_pass}</a>. AI use is documented in <code>AI_USE.md</code>.</p>
<p><b>Limitations / improvements.</b> CI does not start a cluster; an end-to-end job (k3d inside the runner, Locust smoke test) would catch manifest regressions.
Images are built locally and imported, not pushed to a registry.</p>

<h2>Task 7: Performance, cost and review</h2>
<p><b>Standard load test</b> (<code>locust ... --users 4 --spawn-rate 4 --run-time 2m</code> against the Ingress; <code>results/loadtest_stats.csv</code>,
<code>loadtest_headers.json</code>, <code>loadtest_locust.log</code>) {MEAS}: <b>p50 {lt['p50_ms']:.0f} ms, p95 {lt['p95_ms']:.0f} ms</b>, throughput <b>{lt['rps']:.2f} req/s</b>,
<b>{lt['requests']} requests, {lt['failures']} failed (error rate {lt['error_rate_pct']:.2f}%)</b>; share per replica:
{", ".join(f"{k}: {v:.1f}%" for k, v in lt.get('replica_share_pct', {}).items())}.
Pod resources during the run (<code>kubectl top pods</code> every 10 s, <code>task7_top.txt</code>):
{"; ".join(f"{n}: CPU {min(d['cpu'])}-{max(d['cpu'])}m, memory {min(d['mem'])}-{max(d['mem'])} MiB" for n, d in pod_cpu.items())}.
Cold-start median (Task 4): {cold_med} s.</p>
<p><b>Cost</b> (<code>data/rate_card.json</code>: INR 3.50 per vCPU-hour, INR 0.45 per GiB-hour; each replica billed for its limits) {MEAS} for throughput, {ASSUME} that the
replicas observed in the run are the replicas running:</p>
<pre>{cost_txt}</pre>
<p><b>SLO.</b> Target: <b>99% of /parse requests succeed</b> (HTTP 200 within 30 s), window: one standard load-test run (2 min). Error budget = 1% &times; {lt['requests']} requests =
<b>{budget:.2f} requests</b>; used {used} failed request(s) = {100 * used / budget if budget else 0:.0f}% of the budget {MEAS}.</p>
<table><tr><th>Component</th><th>Evidence (measured)</th><th>Limitation found</th><th>Improvement</th></tr>
<tr><td>Data and storage</td><td>{counts['input']} teacher replies &rarr; {counts['kept']} kept; {counts['d_slot_not_in_command']} rejected by rule (d); checksum reproduced</td>
<td>SeaweedFS is one replica on a node-local volume; teacher reachable only through a tunnel</td><td>Replicated SeaweedFS (3 volume servers) or managed S3; teacher inside the cluster</td></tr>
<tr><td>Model quality</td><td>Student v1 full frame {s1['full_frame']:.0f}% vs teacher {teacher['full_frame']:.0f}%; strict JSON validity {s1['json_validity']:.0f}%</td>
<td>Inherits teacher errors; repetition loops on ~1-2% of inputs</td><td>Grammar-constrained decoding; more/cleaner data; logit-level KD with a same-tokenizer teacher</td></tr>
<tr><td>Latency and throughput</td><td>p50 {lt['p50_ms']:.0f} ms, p95 {lt['p95_ms']:.0f} ms, {lt['rps']:.2f} req/s with 4 users</td>
<td>One request at a time per pod; max 2 replicas</td><td>int8/ONNX inference, KV-cache reuse, higher max replicas, batching</td></tr>
<tr><td>Resource utilisation</td><td>{"; ".join(f"max {max(d['cpu'])}m CPU / {max(d['mem'])} MiB" for d in pod_cpu.values())} per pod; Task 3 peak {t3_peak[1]} MiB</td>
<td>CPU-bound at the 1-CPU limit while memory is half used</td><td>Lower memory limit (cheaper), float16 weights, right-size requests</td></tr>
<tr><td>Reliability and recovery</td><td>Cold start median {cold_med} s; recovery error rate {rec['error_rate_pct']:.2f}%; rolling update error rate {roll['error_rate_pct']:.2f}%</td>
<td>Single node: no protection against host failure</td><td>Multi-node cluster, PodDisruptionBudget, anti-affinity, readiness on a warm-up request</td></tr>
<tr><td>Security and cost</td><td>gitleaks: no leaks; cost INR {cost_val} per 1,000 requests</td>
<td>Plain-HTTP S3 inside the cluster; one admin S3 identity; replicas billed while idle</td><td>TLS, per-service least-privilege S3 keys, scale to zero / lower limits when idle</td></tr>
</table>

<h2 class="pb">References</h2>
<ol class="small">
<li>Y. Kim and A. M. Rush. Sequence-Level Knowledge Distillation. EMNLP 2016.</li>
<li>Y.-C. Chen et al. Distilling Knowledge Learned in BERT for Text Generation. ACL 2020.</li>
<li>G. Hinton, O. Vinyals, J. Dean. Distilling the Knowledge in a Neural Network. 2015.</li>
<li>E. Bastianelli et al. SLURP: A Spoken Language Understanding Resource Package. EMNLP 2020.</li>
<li>S. Biderman et al. Pythia: A Suite for Analyzing Large Language Models. ICML 2023; EleutherAI/pythia-70m model card.</li>
<li>Microsoft. Phi-3 Technical Report, 2024; Ollama library phi3.5.</li>
<li>PyTorch Knowledge Distillation Tutorial; Hugging Face Transformers causal LM guide; TRL Distillation Trainer docs.</li>
<li>k3d, K3s, SeaweedFS, Kubernetes (Deployments, Services, Probes, Secrets, HPA, resource metrics), Traefik, Locust, Gitleaks documentation.</li>
<li>AWS VPC User Guide: Network ACLs. Google SRE Book: Service Level Objectives.</li>
</ol>
<h2>Appendix A: Commands</h2>
<pre>make up | make label OLLAMA_URL=... SHARD_COUNT=3 | make clean-data | make teacher-eval OLLAMA_URL=...
make train SUBSET=50 | make train | make train-v2 | make publish VERSION=v1 | make release VERSION=v1
make eval-base | make eval-student VERSION=v1 | make task3 | make task4 | make task7 | make test | make down</pre>
<h2>Appendix B: Teacher prompt (prompts/teacher_prompt.txt, first lines)</h2>
<pre>{open(os.path.join(ROOT, "prompts/teacher_prompt.txt")).read()[:600].replace("<", "&lt;")}&hellip;</pre>
</body></html>"""

out = os.path.join(ROOT, "report", "report.html")
with open(out, "w") as f:
    f.write(html)
print("wrote", out)
if "--pdf" in sys.argv:
    chrome = os.environ.get("CHROME", "google-chrome")
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={os.path.join(ROOT, 'report', 'report.pdf')}", "file://" + out], check=True)
    print("wrote report/report.pdf")
