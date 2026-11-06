import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for sub in ("service", "worker", "tools"):
    sys.path.insert(0, os.path.join(ROOT, sub))
os.chdir(ROOT)
