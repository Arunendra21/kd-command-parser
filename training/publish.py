"""Checksum a trained model and upload it to s3://models/<version>/.

Writes <dir>/model.sha256 (sha256sum format, one line per file; the first line
is model.safetensors, the file published as a GitHub Release asset) and copies
model.sha256 to results/models/<version>/.
"""
import argparse
import hashlib
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "worker"))
import s3util  # noqa: E402

FIRST = "model.safetensors"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--dir", help="default artifacts/<version>")
    ap.add_argument("--no-upload", action="store_true")
    a = ap.parse_args()
    d = a.dir or f"artifacts/{a.version}"
    files = sorted(f for f in os.listdir(d) if f != "model.sha256" and os.path.isfile(os.path.join(d, f)))
    files.sort(key=lambda f: f != FIRST)
    lines = "".join(f"{sha256(os.path.join(d, f))}  {f}\n" for f in files)
    with open(os.path.join(d, "model.sha256"), "w") as f:
        f.write(lines)
    os.makedirs(f"results/models/{a.version}", exist_ok=True)
    shutil.copy(os.path.join(d, "model.sha256"), f"results/models/{a.version}/model.sha256")
    shutil.copy(os.path.join(d, "version.json"), f"results/models/{a.version}/version.json")
    print(lines, end="")
    if a.no_upload:
        return
    s3 = s3util.client()
    for f in files + ["model.sha256"]:
        s3.upload_file(os.path.join(d, f), "models", f"{a.version}/{f}")
        print(f"uploaded s3://models/{a.version}/{f}")


if __name__ == "__main__":
    main()
