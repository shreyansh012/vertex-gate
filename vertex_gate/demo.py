"""An offline demo. Registers five toy versions and gates each one."""

import os

from . import audit, registry
from .gate import GateConfig, run_gate
from .toy import fit_line, fit_mean, make_data, rmse


def build_registry(reg_path):
    """Fill a fresh registry with toy versions. Returns the list of names."""
    train_x, train_y = make_data(seed=1, n=200)
    test_x, test_y = make_data(seed=2, n=100)
    mean_score = rmse(fit_mean(train_x, train_y), test_x, test_y)
    line_score = rmse(fit_line(train_x, train_y), test_x, test_y)

    reg = registry.new_registry()
    registry.add_version(reg, "v1-mean-only", {"rmse": mean_score})
    registry.add_version(reg, "v2-line", {"rmse": line_score})
    registry.add_version(reg, "v3-line-again", {"rmse": line_score})  # a tie
    registry.add_version(reg, "v4-nan", {"rmse": float("nan")})
    registry.add_version(reg, "v5-no-metric", {})
    registry.save(reg_path, reg)
    return [v["version"] for v in reg["versions"]]


def run(folder, force=False):
    """Run the demo in `folder`. Returns a list of (version, Decision).

    Raises RegistryError if registry.json or audit.jsonl already exists in
    `folder`, unless force is True. Nothing is deleted without force.
    """
    os.makedirs(folder, exist_ok=True)
    reg_path = os.path.join(folder, "registry.json")
    audit_path = os.path.join(folder, "audit.jsonl")
    existing = [p for p in (reg_path, audit_path) if os.path.exists(p)]
    if existing and not force:
        raise registry.RegistryError(
            "refusing to overwrite %s (use --force)" % ", ".join(existing))
    for path in existing:
        os.remove(path)

    config = GateConfig(metric="rmse", higher_is_better=False, margin=0.05)
    results = []
    for name in build_registry(reg_path):
        results.append((name, run_gate(reg_path, name, config, audit_path)))
    return results


def main(folder, force=False):
    results = run(folder, force=force)
    print("vertex-gate demo (toy numbers on synthetic data)")
    for name, d in results:
        verdict = "DEPLOY" if d.allow else "BLOCK "
        print("  %s %-14s %-18s %s" % (verdict, name, d.reason, d.detail))
    audit_path = os.path.join(folder, "audit.jsonl")
    print("audit lines written: %d (%s)" % (len(audit.read(audit_path)), audit_path))
    reg = registry.load(os.path.join(folder, "registry.json"))
    print("deployed now: %s" % reg["deployed"])
    return 0
