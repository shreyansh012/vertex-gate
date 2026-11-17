import ast
import itertools
import os
import unittest

from pipeline import kfp_pipeline
from vertex_gate import registry
from vertex_gate.gate import GateConfig, evaluate

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "pipeline", "kfp_pipeline.py")


class PipelineFileTests(unittest.TestCase):
    def test_file_parses_and_is_marked_not_run(self):
        with open(PATH, encoding="utf-8") as handle:
            source = handle.read()
        tree = ast.parse(source)
        self.assertIn("NOT RUN", source)
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        for stage in ("preprocess", "train", "evaluate", "deploy"):
            self.assertIn(stage, names)

    @unittest.skipIf(kfp_pipeline.KFP_AVAILABLE, "kfp is installed")
    def test_build_fails_loudly_without_kfp(self):
        with self.assertRaises(RuntimeError):
            kfp_pipeline.build_pipeline()

    @unittest.skipUnless(kfp_pipeline.KFP_AVAILABLE, "kfp is not installed")
    def test_build_returns_a_callable_with_kfp(self):
        self.assertTrue(callable(kfp_pipeline.build_pipeline()))

    def test_inline_gate_matches_real_gate(self):
        values = [1.0, 2.0, 2.5, float("nan"), float("inf")]
        for cand, cur, has_cur, margin in itertools.product(
                values, values, (True, False), (0.0, 0.5)):
            reg = registry.new_registry()
            registry.add_version(reg, "new", {"rmse": cand})
            if has_cur:
                registry.add_version(reg, "old", {"rmse": cur})
                reg["deployed"] = "old"
            want = evaluate(reg, "new", GateConfig("rmse", False, margin)).allow
            got = kfp_pipeline.gate_decision(cand, cur, has_cur, margin)
            self.assertEqual(got, "true" if want else "false",
                             msg=(cand, cur, has_cur, margin))

    def test_inline_gate_fails_closed_on_junk(self):
        self.assertEqual(kfp_pipeline.gate_decision(None, 1.0, True, 0.0), "false")
        self.assertEqual(kfp_pipeline.gate_decision(1.0, "x", True, 0.0), "false")
        self.assertEqual(kfp_pipeline.gate_decision(1.0, 2.0, True, float("nan")), "false")


if __name__ == "__main__":
    unittest.main()
