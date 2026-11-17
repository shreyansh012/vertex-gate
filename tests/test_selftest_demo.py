import os
import subprocess
import sys
import tempfile
import unittest

from vertex_gate import audit, demo, registry, selftest
from vertex_gate.gate import GateConfig, run_gate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SelfTest(unittest.TestCase):
    def test_every_planted_bad_metric_is_rejected(self):
        results = selftest.run()
        self.assertGreaterEqual(len(results), 6)
        for label, blocked in results:
            self.assertTrue(blocked, msg="gate accepted planted metric: " + label)

    def test_selftest_detects_a_broken_gate(self):
        # Prove the self-test can fail: swap in a gate that lets everything in.
        original = selftest.run_gate

        def lenient(reg_path, candidate, config, audit_path, now=None):
            reg = registry.load(reg_path)
            reg["deployed"] = candidate
            registry.save(reg_path, reg)
            return type("D", (), {"allow": True})()

        selftest.run_gate = lenient
        try:
            self.assertFalse(all(b for _, b in selftest.run()))
        finally:
            selftest.run_gate = original

    def test_planted_metric_in_a_real_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            reg_path = os.path.join(folder, "r.json")
            audit_path = os.path.join(folder, "a.jsonl")
            reg = registry.new_registry()
            registry.add_version(reg, "good", {"rmse": 2.0})
            registry.add_version(reg, "bad", {"rmse": float("nan")})
            reg["deployed"] = "good"
            registry.save(reg_path, reg)
            # NaN survives the round trip through the file.
            d = run_gate(reg_path, "bad", GateConfig(), audit_path)
            self.assertFalse(d.allow)
            self.assertEqual(registry.load(reg_path)["deployed"], "good")


class DemoTest(unittest.TestCase):
    def test_demo_outcomes(self):
        with tempfile.TemporaryDirectory() as folder:
            results = demo.run(folder)
            got = [(n, d.allow, d.reason) for n, d in results]
            self.assertEqual(got, [
                ("v1-mean-only", True, "FIRST_VERSION"),
                ("v2-line", True, "IMPROVED"),
                ("v3-line-again", False, "NO_IMPROVEMENT"),
                ("v4-nan", False, "METRIC_INVALID"),
                ("v5-no-metric", False, "METRIC_MISSING"),
            ])
            self.assertEqual(len(audit.read(os.path.join(folder, "audit.jsonl"))), 5)
            reg = registry.load(os.path.join(folder, "registry.json"))
            self.assertEqual(reg["deployed"], "v2-line")


class DemoSafetyTest(unittest.TestCase):
    def test_demo_run_leaves_existing_files_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            for name in ("registry.json", "audit.jsonl"):
                with open(os.path.join(folder, name), "w", encoding="utf-8") as h:
                    h.write("old " + name)
            with self.assertRaises(registry.RegistryError):
                demo.run(folder)
            for name in ("registry.json", "audit.jsonl"):
                with open(os.path.join(folder, name), encoding="utf-8") as h:
                    self.assertEqual(h.read(), "old " + name)
            demo.run(folder, force=True)  # now it may replace them
            self.assertEqual(len(audit.read(os.path.join(folder, "audit.jsonl"))), 5)


class CommandLineTest(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "vertex_gate", *args],
                              cwd=ROOT, capture_output=True, text=True)

    def test_selftest_command_exits_zero(self):
        proc = self.run_cli("selftest")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("PASS", proc.stdout)

    def test_gate_command_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            reg = os.path.join(folder, "r.json")
            log = os.path.join(folder, "a.jsonl")
            self.assertEqual(self.run_cli("register", reg, "v1", "--metric", "rmse=2.0").returncode, 0)
            self.assertEqual(self.run_cli("register", reg, "v2", "--metric", "rmse=nan").returncode, 0)
            p = self.run_cli("gate", reg, "v1", "--audit", log)
            self.assertEqual(p.returncode, 0)
            self.assertIn("DEPLOY v1 FIRST_VERSION", p.stdout)
            self.assertEqual(p.stderr, "")
            self.assertEqual(len(audit.read(log)), 1)
            p = self.run_cli("gate", reg, "v2", "--audit", log)
            self.assertEqual(p.returncode, 1)
            self.assertIn("BLOCK v2 METRIC_INVALID", p.stdout)
            self.assertEqual(p.stderr, "")
            self.assertEqual(len(audit.read(log)), 2)

    def test_register_leaves_a_damaged_registry_alone(self):
        with tempfile.TemporaryDirectory() as folder:
            reg = os.path.join(folder, "r.json")
            with open(reg, "wb") as handle:
                handle.write(b"{not json")
            p = self.run_cli("register", reg, "vX", "--metric", "rmse=1.0")
            self.assertEqual(p.returncode, 2)
            self.assertIn("error:", p.stderr)
            with open(reg, "rb") as handle:
                self.assertEqual(handle.read(), b"{not json")

    def test_register_duplicate_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as folder:
            reg = os.path.join(folder, "r.json")
            self.assertEqual(self.run_cli("register", reg, "v1").returncode, 0)
            p = self.run_cli("register", reg, "v1")
            self.assertEqual(p.returncode, 2)
            self.assertIn("error:", p.stderr)
            self.assertNotIn("Traceback", p.stderr)

    def test_demo_command_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as folder:
            reg = os.path.join(folder, "registry.json")
            with open(reg, "w", encoding="utf-8") as handle:
                handle.write("keep me")
            p = self.run_cli("demo", "--dir", folder)
            self.assertEqual(p.returncode, 2)
            with open(reg, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "keep me")
            p = self.run_cli("demo", "--dir", folder, "--force")
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
