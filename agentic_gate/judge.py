"""LLM-judge slot. The point is not the model; it's the AUTHORITY model.

A judge starts advisory. It is promoted to 'blocking' (Tier 2 only) only if its measured precision AND recall
on a human-labelled golden set clear the bars in policy/rules.json. Re-run on every policy/prompt/model change.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .catalog import ROOT, Policy

GOLDEN = ROOT / "evals" / "golden.json"


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
