"""Command line: demo, selftest, register, gate."""

import argparse
import os
import sys

from . import demo, registry, selftest
from .gate import GateConfig, run_gate


def _parse_metric(text):
    name, sep, value = text.partition("=")
    if not name or not sep:
        raise argparse.ArgumentTypeError("use NAME=VALUE, for example rmse=1.2")
    try:
        return name, float(value)  # float() accepts "nan" on purpose
    except ValueError:
        raise argparse.ArgumentTypeError("not a number: " + value)


def build_parser():
    p = argparse.ArgumentParser(prog="vertex_gate")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="run the offline demo")
    d.add_argument("--dir", default="demo_out", help="output folder")
    d.add_argument("--force", action="store_true",
                   help="overwrite registry.json and audit.jsonl if present")

    sub.add_parser("selftest", help="plant bad metrics, expect all rejected")

    r = sub.add_parser("register", help="add a version to a registry file")
    r.add_argument("registry")
    r.add_argument("version")
    r.add_argument("--metric", action="append", type=_parse_metric, default=[])

    g = sub.add_parser("gate", help="gate one version; exit 0 only if deployed")
    g.add_argument("registry")
    g.add_argument("version")
    g.add_argument("--audit", default="audit.jsonl")
    g.add_argument("--metric", default="rmse")
    g.add_argument("--higher-is-better", action="store_true")
    g.add_argument("--margin", type=float, default=0.0)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except registry.RegistryError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


def _dispatch(args):
    if args.cmd == "demo":
        return demo.main(args.dir, force=args.force)
    if args.cmd == "selftest":
        return selftest.main()
    if args.cmd == "register":
        # Only a missing file starts a new registry. A damaged one is an error.
        if os.path.exists(args.registry):
            reg = registry.load(args.registry)
        else:
            reg = registry.new_registry()
        registry.add_version(reg, args.version, dict(args.metric))
        registry.save(args.registry, reg)
        print("registered", args.version)
        return 0
    config = GateConfig(args.metric, args.higher_is_better, args.margin)
    d = run_gate(args.registry, args.version, config, args.audit)
    print("%s %s %s %s" % ("DEPLOY" if d.allow else "BLOCK", d.candidate,
                           d.reason, d.detail))
    return 0 if d.allow else 1
