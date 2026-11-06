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

Mistakes or wrong suggestions I caught: _fill in during the work. Examples: wrong flags, a manifest that did not apply, numbers that did not match `results/`._
