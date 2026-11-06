import subprocess
import sys


def test_nacl_passes_sample_packets():
    out = subprocess.run([sys.executable, "tools/nacl_sim.py", "network/nacl.json",
                          "network/packets_sample.jsonl", "--check"], capture_output=True, text=True, check=True).stdout
    assert "WRONG" not in out and "6 / 6" in out
