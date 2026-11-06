# CI evidence

- Passing run (model-v1 from GitHub Release, all stages incl. quality gate): https://github.com/Arunendra21/kd-command-parser/actions/runs/42193828050
- Failing run (deliberately bad model: untrained Pythia-70M), fails at quality gate: https://github.com/Arunendra21/kd-command-parser/actions/runs/42193836249

```

JOBS
✓ lint in 8s (ID 127812050259)
✓ secret-scan in 7s (ID 127812050572)
✓ unit-tests in 48s (ID 127812125133)
✓ evaluate in 2m22s (ID 127812485855)
X quality-gate in 8s (ID 127813501032)
QUALITY GATE FAILED: json_validity 0.0 < 95.0
  "json_validity": 0.0,


JOBS
✓ lint in 6s (ID 127812015754)
✓ secret-scan in 5s (ID 127812016259)
✓ unit-tests in 49s (ID 127812074197)
✓ evaluate in 1m8s (ID 127812433609)
✓ quality-gate in 8s (ID 127812938293)
```
