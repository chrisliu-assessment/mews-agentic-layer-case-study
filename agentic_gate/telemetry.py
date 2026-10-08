"""One canonical event per gate run. This is the dataset that the 10-row spreadsheet was a hand-made preview of."""
from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from .catalog import ROOT, Policy
from .gate import Verdict

OUT = ROOT / "out" / "events.jsonl"


def emit(v: Verdict, m: dict, policy: Policy, path: Path = OUT) -> dict:
    ev = {
        "ts": int(time.time()), "pr_id": v.pr_id, "component": v.component, "tier": v.tier,
        "workflow": policy.canonical_workflow(m.get("workflow")) or "UNKNOWN",
        "workflow_raw": m.get("workflow"), "verdict": v.verdict, "policy_version": policy.version,
        "policy_hash": v.policy, "judge_mode": v.judge_mode, "waiver": v.waiver,
        "rules": [asdict(r) for r in v.results if r.status != "pass"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(ev) + "\n")
    return ev
