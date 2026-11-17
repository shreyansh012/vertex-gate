"""vertex-gate: a metric-gated model deploy that fails closed."""

from .gate import Decision, GateConfig, evaluate, run_gate

__all__ = ["Decision", "GateConfig", "evaluate", "run_gate"]
