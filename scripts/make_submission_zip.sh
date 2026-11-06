#!/usr/bin/env bash
# Build <roll_number>.zip: report, handwritten reflection, source at tag `final`, README with repo link.
set -euo pipefail
ROLL=230103016
REFLECTION="${1:-../$ROLL.pdf}"
[ -f "$REFLECTION" ] || { echo "put the scanned reflection at $REFLECTION first"; exit 1; }
OUT=$(mktemp -d)/$ROLL
mkdir -p "$OUT"
git archive --format=tar --prefix=kd-command-parser/ final | tar -x -C "$OUT"
cp "$REFLECTION" "$OUT/$ROLL.pdf"
cp report/report.pdf "$OUT/report.pdf"
cp README.md "$OUT/README.md"
(cd "$(dirname "$OUT")" && rm -f "$ROLL.zip" && zip -qr "$ROLL.zip" "$ROLL")
mv "$(dirname "$OUT")/$ROLL.zip" "../$ROLL.zip"
unzip -l "../$ROLL.zip" | tail -1; echo "wrote $(cd .. && pwd)/$ROLL.zip"
