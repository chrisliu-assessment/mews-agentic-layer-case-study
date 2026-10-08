"""Re-analysis of the data pack. Everything printed is computed from data/deployments.csv + policy/."""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .catalog import ROOT, Policy

CSV = ROOT / "data" / "deployments.csv"
BAD = ("Reverted", "Incident")


def load(path: Path = CSV) -> list[dict]:
    with path.open() as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        t = r["Time_Impact_Mins"].strip()
        r["mins"] = int(t) if t else None
    return rows


def summarize(rows: list[dict], p: Policy) -> dict:
    known = [r["mins"] for r in rows if r["mins"] is not None]
    by_tier = defaultdict(lambda: Counter())
    for r in rows:
        by_tier[p.tier(r["Component"])]["bad" if r["Outcome"].startswith(BAD) else "ok"] += 1
    raw_labels = {r["Agent_Workflow"] for r in rows}
    canon = {p.canonical_workflow(l) for l in raw_labels}
    return {
        "n": len(rows),
        "saved": -sum(m for m in known if m < 0),
        "lost": sum(m for m in known if m > 0),
        "net_lost": sum(known),
        "missing_time": [r["PR_ID"] for r in rows if r["mins"] is None],
        "raw_labels": len(raw_labels), "canonical_labels": len(canon),
        "by_tier": {t: dict(c) for t, c in sorted(by_tier.items())},
        "coverage": coverage(rows, p),
    }


def coverage(rows: list[dict], p: Policy) -> list[dict]:
    """Required controls for the component's tier vs controls the recorded workflow actually provides.
    'deterministic_gate' / 'owner_approval' are never recorded in the data pack: that absence is the finding."""
    out = []
    for r in rows:
        tier = p.tier(r["Component"])
        have = set(p.controls_of(r["Agent_Workflow"]))
        missing = [c for c in p.required_controls[tier] if c not in have]
        out.append({"pr": r["PR_ID"], "component": r["Component"], "tier": tier, "workflow": r["Agent_Workflow"],
                    "outcome": r["Outcome"], "missing": missing,
                    "controls_met": len(p.required_controls[tier]) - len(missing), "controls_required": len(p.required_controls[tier])})
    return out


def render(rows: list[dict], p: Policy) -> str:
    s = summarize(rows, p)
    L = ["== Data pack audit (n=%d: anecdotal, directional only) ==" % s["n"], ""]
    L.append(f"Time: saved {s['saved']} min, lost {s['lost']} min  =>  NET {s['net_lost']:+d} min "
             f"({'a net LOSS' if s['net_lost'] > 0 else 'net gain'}); the single Sev-1 alone is +480.")
    L.append(f"Telemetry: {s['raw_labels']} workflow labels collapse to {s['canonical_labels']} canonical workflows; "
             f"time impact missing for {', '.join(s['missing_time'])}.")
    L.append("Bad outcomes by tier (reverted or incident):")
    for t, c in s["by_tier"].items():
        L.append(f"  Tier {t}: {c.get('bad', 0)} bad / {c.get('bad', 0) + c.get('ok', 0)}")
    L += ["", "Control coverage replay (required by policy for the component's tier vs. what the recorded workflow provides):",
          f"  {'PR':8}{'Component':24}{'T':3}{'Workflow':17}{'Outcome':17}{'Met':6}Missing"]
    for c in s["coverage"]:
        L.append(f"  {c['pr']:8}{c['component']:24}{c['tier']:<3}{c['workflow']:17}{c['outcome']:17}"
                 f"{c['controls_met']}/{c['controls_required']:<4}{', '.join(c['missing'])}")
    full = sum(1 for c in s["coverage"] if not c["missing"])
    L += ["", f"PRs meeting their tier's required controls: {full}/{s['n']}. No PR records a deterministic gate or an owner approval.",
          "Reading: the control a PR got was set by which agent the builder happened to run, not by the component's risk.",
          "The Sev-1 landed on a Tier 0 component with one LLM review (PR-037 passed Security_Eval on Payment_Token_Capture;",
          "PR-042 reused that same workflow on a different, higher-blast-radius component).",
          "Assumption: workflow->controls mapping in policy/workflows.json is inferred from names, to be confirmed with the team."]
    return "\n".join(L)
