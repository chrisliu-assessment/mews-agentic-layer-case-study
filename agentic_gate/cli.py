from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import audit
from .catalog import ROOT, Policy
from .gate import evaluate
from .judge import KeywordJudge, approve, calibrate
from .telemetry import emit

ICON = {"PASS": "PASS ", "PASS_WITH_WARNINGS": "WARN ", "PASS_WITH_WAIVER": "WAIVE", "BLOCK": "BLOCK"}


def show(v) -> None:
    print(f"[{ICON[v.verdict]}] {v.pr_id}  {v.component} (Tier {v.tier})  policy={v.policy}  judge={v.judge_mode}")
    for r in v.results:
        if r.status != "pass":
            print(f"        {r.status.upper():7}{r.id:9}{r.reason}")
    for f in v.judge_findings:
        print(f"        ADVISE {f}")


def run_check(path: Path, p: Policy, waive: dict | None = None):
    m = json.loads(path.read_text())
    v = evaluate(m, p, KeywordJudge(), waive)
    emit(v, m, p)
    show(v)
    return v


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agentic_gate")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit", help="analyse the data pack")
    c = sub.add_parser("check", help="gate one change manifest (exit 1 on BLOCK)")
    c.add_argument("manifest")
    c.add_argument("--waive", nargs="+", metavar="RULE")
    c.add_argument("--reason")
    c.add_argument("--approver", help="recorded as-is for audit; this prototype does not verify the approver's "
                                       "identity or authority (no GitHub/team-identity check -- see README)")
    sub.add_parser("calibrate", help="measure the judge against the golden set")
    sub.add_parser("demo", help="gate every fixture")
    a = ap.parse_args(argv)
    p = Policy()

    if a.cmd == "audit":
        print(audit.render(audit.load(), p))
    elif a.cmd == "calibrate":
        judge = KeywordJudge()
        cal = calibrate(judge, p)
        b = p.judge_bars
        print(f"judge={judge.name}  precision={cal.precision} (bar {b['min_precision']})  recall={cal.recall} (bar {b['min_recall']})")
        print(f"=> authority: {cal.mode.upper()}")
        for x in cal.missed:
            print(f"   missed: {x}")
        auth = approve(judge, p, cal)
        print(f"approved -> evals/judge_authority.json (judge={auth.judge}, policy={auth.policy_hash}). "
              f"The gate reads this record; it is not recalibrated per PR.")
    elif a.cmd == "check":
        waive = {"rules": a.waive, "reason": a.reason, "approver": a.approver} if a.waive else None
        if waive and not (a.reason and a.approver):
            ap.error("--waive requires --reason and --approver")
        return 1 if run_check(Path(a.manifest), p, waive).blocked else 0
    elif a.cmd == "demo":
        print(f"policy {p.version} ({p.hash})\n")
        verdicts = [run_check(f, p) for f in sorted((ROOT / "fixtures").glob("*.json"))]
        print(f"\n{sum(v.blocked for v in verdicts)} of {len(verdicts)} blocked. Events appended to out/events.jsonl")
    return 0


if __name__ == "__main__":
    sys.exit(main())
