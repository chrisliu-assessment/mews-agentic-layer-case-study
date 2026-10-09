"""LLM-judge slot. The point is not the model; it's the AUTHORITY model.

A judge starts advisory. It is promoted to 'blocking' (Tier 2 only) only if its measured precision AND recall
on a human-labelled golden set clear the bars in policy/rules.json.

Calibration is an offline, versioned step (`make calibrate`), run whenever the model/prompt/policy changes --
not on every gate execution. It writes an approved authority record to evals/judge_authority.json, pinned to
the judge name and the policy hash it was measured against. The runtime gate (gate.evaluate) only reads that
record; it never calls calibrate() itself, so a real model-backed judge costs one model-free dict lookup per
PR, not a fresh set of golden-set calls. A record that doesn't match the current judge/policy is stale and the
gate fails closed to advisory until someone re-runs `make calibrate`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .catalog import ROOT, Policy

GOLDEN = ROOT / "evals" / "golden.json"
AUTHORITY = ROOT / "evals" / "judge_authority.json"


class Judge:
    name = "abstract"

    def review(self, diff: str) -> list[str]:  # returns findings
        raise NotImplementedError


class KeywordJudge(Judge):
    """Offline stand-in for a real model. Deliberately naive: catches syntactic smells, misses semantic bugs.
    Swap for an API-backed judge by implementing review(); the calibration + authority logic is unchanged."""
    name = "keyword-judge-v0"
    SMELLS = ("except:", "eval(", "TODO", "exec(", "verify=False")

    def review(self, diff: str) -> list[str]:
        return [f"smell: {s}" for s in self.SMELLS if s in diff]


@dataclass
class Calibration:
    precision: float
    recall: float
    tp: int
    fp: int
    fn: int
    missed: list[str]
    mode: str  # blocking | advisory


def calibrate(judge: Judge, policy: Policy, golden_path: Path = GOLDEN) -> Calibration:
    cases = json.loads(golden_path.read_text())["cases"]
    tp = fp = fn = 0
    missed = []
    for c in cases:
        flagged = bool(judge.review(c["diff"]))
        if flagged and c["has_issue"]:
            tp += 1
        elif flagged:
            fp += 1
        elif c["has_issue"]:
            fn += 1
            missed.append(f'{c["id"]}: {c["why"]}')
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    bars = policy.judge_bars
    ok = precision >= bars["min_precision"] and recall >= bars["min_recall"]
    return Calibration(round(precision, 2), round(recall, 2), tp, fp, fn, missed, "blocking" if ok else "advisory")


@dataclass
class Authority:
    judge: str
    policy_hash: str
    mode: str  # blocking | advisory
    precision: float
    recall: float
    calibrated_at: str


def approve(judge: Judge, policy: Policy, cal: Calibration, path: Path = AUTHORITY) -> Authority:
    """Persist a calibration result as the approved authority record for this judge+policy pair."""
    auth = Authority(judge.name, policy.hash, cal.mode, cal.precision, cal.recall,
                      datetime.now(timezone.utc).isoformat())
    path.write_text(json.dumps(asdict(auth), indent=2) + "\n")
    return auth


def load_authority(judge: Judge, policy: Policy, path: Path = AUTHORITY) -> Authority:
    """Read the last approved calibration. Fails closed to advisory if none exists yet, or if it was
    measured against a different judge or a different policy hash (stale -- re-run `make calibrate`)."""
    if path.exists():
        data = json.loads(path.read_text())
        if data.get("judge") == judge.name and data.get("policy_hash") == policy.hash:
            return Authority(**data)
    return Authority(judge.name, policy.hash, "advisory", 0.0, 0.0, "")
