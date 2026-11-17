"""The gate. It decides if a model version may be deployed.

Rules:
  1. If nothing is deployed yet, the first version deploys.
  2. Otherwise the candidate must beat the deployed version by MORE than
     the margin. A tie is not a win.
  3. A missing, NaN, infinite or non-number metric blocks the deploy.
  4. If the gate itself cannot run, the answer is "blocked".
  5. Every decision is written to the audit log before anything deploys.
"""

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from . import audit, registry

# Reason codes.
FIRST_VERSION = "FIRST_VERSION"
IMPROVED = "IMPROVED"
NO_IMPROVEMENT = "NO_IMPROVEMENT"
METRIC_MISSING = "METRIC_MISSING"
METRIC_INVALID = "METRIC_INVALID"
CURRENT_METRIC_BAD = "CURRENT_METRIC_BAD"
CANDIDATE_NOT_FOUND = "CANDIDATE_NOT_FOUND"
ALREADY_DEPLOYED = "ALREADY_DEPLOYED"
CONFIG_INVALID = "CONFIG_INVALID"
REGISTRY_INVALID = "REGISTRY_INVALID"
GATE_ERROR = "GATE_ERROR"
AUDIT_FAILED = "AUDIT_FAILED"
DEPLOY_FAILED = "DEPLOY_FAILED"


def is_number(value):
    """True for a real, finite number. Booleans do not count."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(value)


@dataclass(frozen=True)
class GateConfig:
    metric: str = "rmse"
    higher_is_better: bool = False
    margin: float = 0.0

    def problem(self):
        """Return a text problem with the config, or None if it is fine."""
        if not isinstance(self.metric, str) or not self.metric:
            return "metric must be a non-empty name"
        if not isinstance(self.higher_is_better, bool):
            return "higher_is_better must be true or false"
        if not is_number(self.margin) or self.margin < 0:
            return "margin must be a finite number, zero or more"
        return None


@dataclass
class Decision:
    allow: bool
    reason: str
    candidate: str
    current: object = None
    detail: str = ""
    candidate_value: object = None
    current_value: object = None
    config: dict = field(default_factory=dict)


def _config_dict(config):
    try:
        return asdict(config)
    except TypeError:
        return {"repr": repr(config)}


def _block(reason, candidate, config, **kw):
    return Decision(False, reason, candidate, config=_config_dict(config), **kw)


def evaluate(reg, candidate, config):
    """Decide about one candidate. Pure: no files, no side effects.

    Any unexpected error becomes a "blocked" decision (fail closed).
    """
    try:
        return _evaluate(reg, candidate, config)
    except Exception as exc:  # noqa: BLE001 - fail closed on anything
        return _block(GATE_ERROR, str(candidate), config,
                      detail="%s: %s" % (type(exc).__name__, exc))


def _metric(item, name):
    metrics = item.get("metrics") if isinstance(item, dict) else None
    if not isinstance(metrics, dict):
        return None
    return metrics.get(name)


def _evaluate(reg, candidate, config):
    if not isinstance(config, GateConfig):
        return _block(CONFIG_INVALID, str(candidate), config,
                      detail="config is not a GateConfig")
    problem = config.problem()
    if problem:
        return _block(CONFIG_INVALID, str(candidate), config, detail=problem)
    registry.validate(reg)

    cand = registry.find(reg, candidate)
    if cand is None:
        return _block(CANDIDATE_NOT_FOUND, str(candidate), config,
                      detail="no such version in the registry")

    current = reg.get("deployed")
    if current == candidate:
        return _block(ALREADY_DEPLOYED, candidate, config, current=current,
                      detail="this version is already deployed")

    cand_value = _metric(cand, config.metric)

    if current is None:
        # Rule 1: the first version always deploys. We still note a bad metric.
        note = "first version"
        if not is_number(cand_value):
            note += " (warning: its metric is missing or invalid)"
        return Decision(True, FIRST_VERSION, candidate, detail=note,
                        candidate_value=cand_value,
                        config=_config_dict(config))

    if cand_value is None:
        return _block(METRIC_MISSING, candidate, config, current=current,
                      detail="candidate has no '%s' metric" % config.metric)
    if not is_number(cand_value):
        return _block(METRIC_INVALID, candidate, config, current=current,
                      candidate_value=cand_value,
                      detail="candidate metric is not a finite number")

    cur_item = registry.find(reg, current)
    cur_value = _metric(cur_item, config.metric) if cur_item else None
    if not is_number(cur_value):
        return _block(CURRENT_METRIC_BAD, candidate, config, current=current,
                      candidate_value=cand_value, current_value=cur_value,
                      detail="deployed version has no usable metric to compare")

    if config.higher_is_better:
        gain = cand_value - cur_value
    else:
        gain = cur_value - cand_value
    if gain > config.margin:
        return Decision(True, IMPROVED, candidate, current=current,
                        candidate_value=cand_value, current_value=cur_value,
                        detail="gain %r beats margin %r" % (gain, config.margin),
                        config=_config_dict(config))
    return _block(NO_IMPROVEMENT, candidate, config, current=current,
                  candidate_value=cand_value, current_value=cur_value,
                  detail="gain %r does not beat margin %r (a tie is a block)"
                         % (gain, config.margin))


def _record(event, decision, now):
    rec = asdict(decision)
    rec["event"] = event
    rec["time"] = now.isoformat()
    return rec


def run_gate(registry_path, candidate, config, audit_path, now=None):
    """Gate, log, then deploy. Returns the final Decision.

    Order matters: the audit line is written BEFORE the registry changes.
    If the audit write fails, nothing deploys.
    """
    now = now or datetime.now(timezone.utc)
    reg = None
    try:
        reg = registry.load(registry_path)
    except Exception as exc:  # noqa: BLE001
        decision = _block(REGISTRY_INVALID, str(candidate), config,
                          detail=str(exc))
    else:
        decision = evaluate(reg, candidate, config)

    try:
        audit.write(audit_path, _record("decision", decision, now))
    except Exception as exc:  # noqa: BLE001
        return _block(AUDIT_FAILED, str(candidate), config,
                      detail="cannot write audit log: %s" % exc)

    if not decision.allow:
        return decision

    try:
        reg["deployed"] = decision.candidate
        registry.save(registry_path, reg)
    except Exception as exc:  # noqa: BLE001
        failed = _block(DEPLOY_FAILED, decision.candidate, config,
                        current=decision.current,
                        detail="cannot update registry: %s" % exc)
        try:
            audit.write(audit_path, _record("deploy_failed", failed, now))
        except Exception:  # noqa: BLE001 - nothing more we can do
            pass
        return failed
    return decision
