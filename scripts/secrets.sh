#!/usr/bin/env bash
# Generate S3 credentials once (kept in .secrets/, never committed) and load them
# into Kubernetes Secrets: SeaweedFS identity config (data) and client creds (pipeline, app).
set -euo pipefail
mkdir -p .secrets
if [ ! -f .secrets/s3.env ]; then
  cat > .secrets/s3.env <<EOT
AWS_ACCESS_KEY_ID=kd$(openssl rand -hex 8)
AWS_SECRET_ACCESS_KEY=$(openssl rand -hex 24)
AWS_DEFAULT_REGION=us-east-1
EOT
  chmod 600 .secrets/s3.env
  echo "generated .secrets/s3.env"
fi
set -a; . .secrets/s3.env; set +a
cat > .secrets/s3.json <<EOT
{"identities": [{"name": "admin",
  "credentials": [{"accessKey": "$AWS_ACCESS_KEY_ID", "secretKey": "$AWS_SECRET_ACCESS_KEY"}],
  "actions": ["Admin", "Read", "Write", "List", "Tagging"]}]}
EOT
kubectl -n data create secret generic seaweedfs-s3-config --from-file=s3.json=.secrets/s3.json \
  --dry-run=client -o yaml | kubectl apply -f -
for ns in pipeline app; do
  kubectl -n "$ns" create secret generic s3-credentials --from-env-file=.secrets/s3.env \
    --dry-run=client -o yaml | kubectl apply -f -
done
