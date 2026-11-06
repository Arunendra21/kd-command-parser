# AI use

The handout permits AI tools ("use it with your eyes wide open"). This file records which tools I used, what I used them for, and how I checked the output.

| Tool | Used for | How I checked it |
|---|---|---|
| Claude (Claude Code, Anthropic) | Reading the handout and kit; planning where to run each part without a capable laptop (Codespaces + free Colab GPU); drafting the repository scaffolding: Makefile, Kubernetes manifests, worker/clean/train/predict scripts, FastAPI service, tests, CI workflow, evidence scripts; computing the subnet table; drafting report text from the files in `results/` | Ran every script end to end. Unit tests (`make test`) and CI pass. Checked the cleaning counts with `clean.py`'s sum assertion and the shard coverage with `scripts/check_shards.py`. Re-ran `nacl_sim.py --check` on the sample packets. Recomputed the subnet table by hand. Every number in the report was compared with the raw file in `results/` it came from. |
| Phi-3.5-mini (Ollama) | The teacher model, as the assignment requires (not an assistant) | Its replies are stored unchanged in `results/teacher_shards/`. Bad replies are removed only by the rules in `clean.py`. |

What I did not use AI for:
- No labels were written by hand or by any model other than the teacher.
- No result was typed in. All results come from the scripts.
- The handwritten reflection is my own.

Mistakes and wrong suggestions caught while checking the AI-generated work:
- The first version of `make label` used `kubectl wait --for=condition=complete`. It hangs forever when the Job fails, so it was replaced by a loop that also detects the `Failed` condition.
- The cold-start timer parsed Kubernetes UTC timestamps as local time (IST) and measured nothing. Fixed with an explicit UTC timezone.
- On my laptop (83% disk use) the kubelet garbage-collected the locally imported images (`ErrImageNeverPull`). Fixed with kubelet image-GC flags in `cluster/k3d.yaml`.
- `kill` and `pkill -f` patterns matched the shell running the command. Processes are now stopped by PID.
- The Task 4 evidence script sent its curl checks to `localhost:8080`, which on my laptop is another application. Now it uses `LOCUST_HOST`.
- An AI-suggested fix for the student's repetition loops (retry with `repetition_penalty=1.3`) was tested on 500 commands and fixed 0 of 5 failures, because JSON repeats tokens by design. It was rejected in favour of the deterministic salvage step in `service/core.py`. The failed attempt is described in the report.
- Every number in the report was checked against the file in `results/` it came from.
