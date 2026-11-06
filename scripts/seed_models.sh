#!/usr/bin/env bash
# Make sure s3://models/<v>/ holds each model version. Source, in order:
# local artifacts/<v>/ (just trained) or the GitHub Release model-<v> (fresh clone).
# Release files are verified against model.sha256 before upload.
set -euo pipefail
REPO="${GITHUB_REPO:?}"
for v in v1 v2; do
  if docker run --rm --network host --env-file .secrets/s3.env -e S3_ENDPOINT=http://localhost:8333 \
       -v "$PWD":/repo -w /repo/worker kd-worker:1.0 \
       python -c "import s3util,sys; s=s3util.client(); sys.exit(0 if s3util.exists(s,'models','$v/model.safetensors') else 1)"; then
    echo "s3://models/$v already present"; continue
  fi
  dir="artifacts/$v"
  if [ ! -f "$dir/model.safetensors" ]; then
    echo "downloading model-$v from GitHub Release $REPO"
    mkdir -p "$dir"
    base="https://github.com/$REPO/releases/download/model-$v"
    curl -fsSL -o "$dir/model.sha256" "$base/model.sha256" || { echo "no release model-$v yet; skipping"; continue; }
    for f in $(awk '{print $2}' "$dir/model.sha256"); do curl -fsSL -o "$dir/$f" "$base/$f"; done
    (cd "$dir" && sha256sum -c model.sha256)
  fi
  docker run --rm --network host --env-file .secrets/s3.env -e S3_ENDPOINT=http://localhost:8333 \
    -v "$PWD":/repo -w /repo/worker kd-worker:1.0 \
    python -c "
import os, s3util
s = s3util.client()
d = '/repo/$dir'
for f in sorted(os.listdir(d)):
    s.upload_file(os.path.join(d, f), 'models', '$v/' + f); print('uploaded s3://models/$v/' + f)"
done
