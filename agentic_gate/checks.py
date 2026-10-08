"""Deterministic checks. Pure functions of (manifest, policy): same input, same verdict, every time.

A manifest is the machine-readable description of a change (in production: built from the PR + diff by CI).
Each check returns None when satisfied, or a short human-readable reason when violated.
"""
from __future__ import annotations

import fnmatch
import re

from .catalog import Policy

SECRET_RES = [re.compile(p) for p in (r"AKIA[0-9A-Z]{16}", r"sk_live_[0-9a-zA-Z]{16,}", r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")]
PAN_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
LOG_RE = re.compile(r"(log|logger|print)\w*\s*[.(].*\b(card|pan|cvv|cvc|token)\w*", re.I)
IMPORT_RE = re.compile(r"^\+\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))")
BOT_APPROVERS = ("bot", "agent", "llm", "claude", "copilot")


def added_lines(m: dict) -> list[tuple[str, str]]:
    return [(f["path"], ln) for f in m.get("files", []) for ln in f.get("diff", "").splitlines() if ln.startswith("+")]


def luhn(digits: str) -> bool:
    s, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d * 2 > 9 else d * 2
        s, alt = s + d, not alt
    return s % 10 == 0


def sec_001(m, p: Policy):
    for path, ln in added_lines(m):
        if any(r.search(ln) for r in SECRET_RES):
            return f"secret-like value in {path}"
        for hit in PAN_RE.finditer(ln):
            digits = re.sub(r"\D", "", hit.group(0))
            if 13 <= len(digits) <= 19 and luhn(digits):
                return f"Luhn-valid card number in {path}"


def sec_002(m, p: Policy):
    for path, ln in added_lines(m):
        if LOG_RE.search(ln):
            return f"card/token field logged in {path}: {ln[1:].strip()[:60]}"


def arch_001(m, p: Policy):
    banned = p.components.get(m["component"], {}).get("may_not_import", [])
    for path, ln in added_lines(m):
        hit = IMPORT_RE.match(ln)
        mod = (hit.group(1) or hit.group(2)) if hit else None
        if mod and any(fnmatch.fnmatch(mod, pat) for pat in banned):
            return f"{m['component']} may not import '{mod}' ({path})"


def _is_test(path: str) -> bool:
    return "/tests/" in f"/{path}" or path.split("/")[-1].startswith("test_")


def test_001(m, p: Policy):
    files = m.get("files", [])
    src = [f for f in files if not _is_test(f["path"])]
    tests = [f for f in files if _is_test(f["path"])]
    if src and not tests:
        return "source changed with no test changes"
    if p.tier(m["component"]) == 0 and not any("contract" in f["path"] for f in tests):
        return "Tier 0 change has no contract test"


def ops_001(m, p: Policy):
    r = m.get("rollout") or {}
    if not r.get("flag"):
        return "no feature flag for rollout"
    if p.tier(m["component"]) == 0 and not (0 < r.get("canary_pct", 100) <= 5):
        return f"Tier 0 canary must be <=5% (got {r.get('canary_pct', 'unset')})"


def own_001(m, p: Policy):
    owner = p.owner(m["component"])
    humans = [a for a in m.get("approvals", []) if not any(b in a.lower() for b in BOT_APPROVERS)]
    if owner not in humans:
        return f"needs sign-off from {owner} (a human; model approvals do not count)"


def tel_001(m, p: Policy):
    problems = []
    if not p.canonical_workflow(m.get("workflow")):
        problems.append(f"unknown workflow '{m.get('workflow')}'")
    if m.get("time_impact_mins") is None:
        problems.append("time_impact_mins missing")
    return "; ".join(problems) or None


CHECKS = {"SEC-001": sec_001, "SEC-002": sec_002, "ARCH-001": arch_001, "TEST-001": test_001,
          "OPS-001": ops_001, "OWN-001": own_001, "TEL-001": tel_001}
