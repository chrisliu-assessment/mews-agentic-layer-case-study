"""Orchestrates tier lookup -> applicable rules -> verdict. The only place a verdict is decided."""
from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import Policy
from .checks import CHECKS, added_lines
from .judge import Judge, calibrate


@dataclass
class RuleResult:
    id: str
    status: str  # pass | fail | warn | waived
    reason: str = ""
    severity: str = ""


@dataclass
class Verdict:
    pr_id: str
    component: str
    tier: int
    verdict: str  # PASS | PASS_WITH_WARNINGS | PASS_WITH_WAIVER | BLOCK
    results: list[RuleResult] = field(default_factory=list)
    judge_mode: str = "none"
    judge_findings: list[str] = field(default_factory=list)
    policy: str = ""
    waiver: dict | None = None

    @property
    def blocked(self) -> bool:
        return self.verdict == "BLOCK"


def evaluate(m: dict, policy: Policy, judge: Judge | None = None, waive: dict | None = None) -> Verdict:
    tier = policy.tier(m["component"])
    results: list[RuleResult] = []
    waived_any = False
    for rid, rule in policy.rules.items():
        if tier not in rule["tiers"]:
            continue
        reason = CHECKS[rid](m, policy)
        if reason is None:
            results.append(RuleResult(rid, "pass", severity=rule["severity"]))
        elif rule["severity"] == "warn":
            results.append(RuleResult(rid, "warn", reason, "warn"))
        elif waive and rule["waivable"] and rid in waive.get("rules", []):
            results.append(RuleResult(rid, "waived", f"{reason} [waived by {waive['approver']}: {waive['reason']}]", "block"))
            waived_any = True
        else:
            results.append(RuleResult(rid, "fail", reason, "block"))

    judge_mode, findings = "none", []
    if judge:
        cal = calibrate(judge, policy)
        # Authority is earned, tier-limited, and can only ADD blocks on Tier 2. It never removes one.
        judge_mode = "blocking" if (cal.mode == "blocking" and tier == 2) else "advisory"
        findings = judge.review("\n".join(ln for _, ln in added_lines(m)))
        if findings and judge_mode == "blocking":
            results.append(RuleResult("JUDGE-001", "fail", "; ".join(findings), "block"))

    if any(r.status == "fail" for r in results):
        verdict = "BLOCK"
    elif waived_any:
        verdict = "PASS_WITH_WAIVER"
    elif any(r.status == "warn" for r in results):
        verdict = "PASS_WITH_WARNINGS"
    else:
        verdict = "PASS"
    return Verdict(m.get("pr_id", "?"), m["component"], tier, verdict, results, judge_mode, findings, policy.hash,
                   waive if waived_any else None)
