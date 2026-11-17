import os
import tempfile
import unittest

from vertex_gate import audit, registry
from vertex_gate.gate import (ALREADY_DEPLOYED, AUDIT_FAILED, CANDIDATE_NOT_FOUND,
                              CONFIG_INVALID, CURRENT_METRIC_BAD, FIRST_VERSION,
                              IMPROVED, METRIC_INVALID, METRIC_MISSING,
                              NO_IMPROVEMENT, REGISTRY_INVALID, GateConfig,
                              evaluate, run_gate)

LOWER = GateConfig(metric="rmse", higher_is_better=False, margin=0.0)


def make_reg(deployed, **versions):
    reg = registry.new_registry()
    for name, metrics in versions.items():
        registry.add_version(reg, name, metrics)
    reg["deployed"] = deployed
    return reg


class RuleTests(unittest.TestCase):
    def test_first_version_deploys(self):
        d = evaluate(make_reg(None, v1={"rmse": 5.0}), "v1", LOWER)
        self.assertTrue(d.allow)
        self.assertEqual(d.reason, FIRST_VERSION)

    def test_improvement_deploys(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 4.0})
        d = evaluate(reg, "v2", LOWER)
        self.assertTrue(d.allow)
        self.assertEqual(d.reason, IMPROVED)

    def test_no_improvement_blocks(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 6.0})
        d = evaluate(reg, "v2", LOWER)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, NO_IMPROVEMENT)

    def test_tie_blocks_even_with_zero_margin(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 5.0})
        d = evaluate(reg, "v2", LOWER)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, NO_IMPROVEMENT)

    def test_gain_equal_to_margin_blocks(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 4.5})
        cfg = GateConfig("rmse", False, 0.5)
        self.assertFalse(evaluate(reg, "v2", cfg).allow)

    def test_gain_above_margin_deploys(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 4.4})
        cfg = GateConfig("rmse", False, 0.5)
        self.assertTrue(evaluate(reg, "v2", cfg).allow)

    def test_higher_is_better(self):
        reg = make_reg("v1", v1={"auc": 0.7}, v2={"auc": 0.8})
        cfg = GateConfig("auc", True, 0.05)
        self.assertTrue(evaluate(reg, "v2", cfg).allow)
        reg = make_reg("v1", v1={"auc": 0.8}, v2={"auc": 0.7})
        self.assertFalse(evaluate(reg, "v2", cfg).allow)

    def test_nan_blocks(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": float("nan")})
        d = evaluate(reg, "v2", LOWER)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, METRIC_INVALID)

    def test_missing_metric_blocks(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={})
        d = evaluate(reg, "v2", LOWER)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, METRIC_MISSING)

    def test_metrics_field_missing_or_wrong_type_blocks(self):
        reg = make_reg("v1", v1={"rmse": 5.0})
        reg["versions"].append({"version": "v2"})
        reg["versions"].append({"version": "v3", "metrics": "oops"})
        self.assertFalse(evaluate(reg, "v2", LOWER).allow)
        self.assertFalse(evaluate(reg, "v3", LOWER).allow)

    def test_malformed_values_block(self):
        for bad in (float("inf"), float("-inf"), "1.0", True, [1.0], {"a": 1}):
            reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": bad})
            d = evaluate(reg, "v2", LOWER)
            self.assertFalse(d.allow, msg=repr(bad))
            self.assertEqual(d.reason, METRIC_INVALID, msg=repr(bad))

    def test_bad_current_metric_blocks(self):
        reg = make_reg("v1", v1={"rmse": float("nan")}, v2={"rmse": 1.0})
        d = evaluate(reg, "v2", LOWER)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, CURRENT_METRIC_BAD)

    def test_deployed_name_not_in_registry_blocks(self):
        reg = make_reg("ghost", v2={"rmse": 1.0})
        self.assertFalse(evaluate(reg, "v2", LOWER).allow)

    def test_unknown_candidate_blocks(self):
        d = evaluate(make_reg(None, v1={"rmse": 1.0}), "nope", LOWER)
        self.assertEqual(d.reason, CANDIDATE_NOT_FOUND)

    def test_already_deployed_blocks(self):
        d = evaluate(make_reg("v1", v1={"rmse": 1.0}), "v1", LOWER)
        self.assertEqual(d.reason, ALREADY_DEPLOYED)

    def test_bad_config_blocks(self):
        reg = make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 1.0})
        for cfg in (GateConfig("rmse", False, float("nan")),
                    GateConfig("rmse", False, -1.0),
                    GateConfig("", False, 0.0),
                    GateConfig("rmse", "yes", 0.0),
                    "not a config", None):
            d = evaluate(reg, "v2", cfg)
            self.assertFalse(d.allow, msg=repr(cfg))
            self.assertEqual(d.reason, CONFIG_INVALID, msg=repr(cfg))

    def test_broken_registry_object_blocks(self):
        for reg in (None, [], {"versions": "x"}, {"versions": [1]}):
            self.assertFalse(evaluate(reg, "v1", LOWER).allow)


class RunGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.reg_path = os.path.join(self._tmp.name, "registry.json")
        self.audit_path = os.path.join(self._tmp.name, "audit.jsonl")

    def save(self, reg):
        registry.save(self.reg_path, reg)

    def test_deploy_updates_registry_and_audit(self):
        self.save(make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 4.0}))
        d = run_gate(self.reg_path, "v2", LOWER, self.audit_path)
        self.assertTrue(d.allow)
        self.assertEqual(registry.load(self.reg_path)["deployed"], "v2")
        lines = audit.read(self.audit_path)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["reason"], IMPROVED)
        self.assertTrue(lines[0]["allow"])

    def test_block_leaves_registry_alone_and_is_logged(self):
        self.save(make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": float("nan")}))
        d = run_gate(self.reg_path, "v2", LOWER, self.audit_path)
        self.assertFalse(d.allow)
        self.assertEqual(registry.load(self.reg_path)["deployed"], "v1")
        lines = audit.read(self.audit_path)
        self.assertEqual(lines[0]["reason"], METRIC_INVALID)
        self.assertEqual(lines[0]["candidate_value"], "nan")

    def test_audit_appends_one_line_per_decision(self):
        self.save(make_reg(None, v1={"rmse": 5.0}, v2={"rmse": 4.0},
                           v3={"rmse": 9.0}))
        for name in ("v1", "v2", "v3"):
            run_gate(self.reg_path, name, LOWER, self.audit_path)
        lines = audit.read(self.audit_path)
        self.assertEqual([x["allow"] for x in lines], [True, True, False])
        self.assertEqual(registry.load(self.reg_path)["deployed"], "v2")

    def test_missing_registry_file_blocks_and_is_logged(self):
        d = run_gate(self.reg_path, "v1", LOWER, self.audit_path)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, REGISTRY_INVALID)
        self.assertEqual(audit.read(self.audit_path)[0]["reason"],
                         REGISTRY_INVALID)

    def test_corrupt_registry_file_blocks(self):
        with open(self.reg_path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        d = run_gate(self.reg_path, "v1", LOWER, self.audit_path)
        self.assertEqual(d.reason, REGISTRY_INVALID)

    def test_audit_failure_blocks_deploy(self):
        self.save(make_reg("v1", v1={"rmse": 5.0}, v2={"rmse": 1.0}))
        bad_audit = os.path.join(self._tmp.name, "a-folder")
        os.mkdir(bad_audit)  # cannot open a folder as a file
        d = run_gate(self.reg_path, "v2", LOWER, bad_audit)
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, AUDIT_FAILED)
        self.assertEqual(registry.load(self.reg_path)["deployed"], "v1")


if __name__ == "__main__":
    unittest.main()
