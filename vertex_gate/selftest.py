"""Self-test: plant bad metrics and prove the gate rejects every one.

Exit code 0 means every planted bad metric was blocked.
"""

import os
import tempfile

from . import registry
from .gate import GateConfig, run_gate

BAD_VALUES = {
    "nan": float("nan"),
    "infinity": float("inf"),
    "text": "0.1",
    "true": True,
    "none": None,
    "list": [0.1],
}


def run():
    """Return a list of (label, was_blocked)."""
    config = GateConfig(metric="rmse", higher_is_better=False, margin=0.0)
    out = []
    with tempfile.TemporaryDirectory() as folder:
        for label, bad in BAD_VALUES.items():
            reg_path = os.path.join(folder, label + "-registry.json")
            audit_path = os.path.join(folder, label + "-audit.jsonl")
            reg = registry.new_registry()
            registry.add_version(reg, "good", {"rmse": 1.0})
            registry.add_version(reg, "planted", {"rmse": bad})
            reg["deployed"] = "good"
            registry.save(reg_path, reg)
            decision = run_gate(reg_path, "planted", config, audit_path)
            still = registry.load(reg_path)["deployed"]
            out.append((label, (not decision.allow) and still == "good"))
    return out


def main():
    results = run()
    for label, blocked in results:
        print("  planted %-9s %s" % (label, "blocked" if blocked else "ACCEPTED (bug)"))
    ok = all(b for _, b in results)
    print("selftest: %s" % ("PASS, every bad metric was rejected" if ok else "FAIL"))
    return 0 if ok else 1
