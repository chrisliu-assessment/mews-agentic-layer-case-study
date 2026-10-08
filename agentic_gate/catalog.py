"""Loads the policy files and fingerprints them so every verdict is traceable to an exact policy version."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY_DIR = ROOT / "policy"
_FILES = ("components.json", "rules.json", "workflows.json", "controls.json")


class Policy:
    def __init__(self, policy_dir: Path = POLICY_DIR):
        raw = {n: (policy_dir / n).read_bytes() for n in _FILES}
        self.hash = hashlib.sha256(b"".join(raw[n] for n in _FILES)).hexdigest()[:12]
        comp, rules, wf, ctl = (json.loads(raw[n]) for n in _FILES)
        self.components = comp["components"]
        self.version = rules["version"]
        self.rules = {r["id"]: r for r in rules["rules"]}
        self.judge_bars = rules["judge"]
        self.required_controls = {int(k): v for k, v in ctl["required_controls"].items()}
        self._alias = {a: cid for cid, w in wf["workflows"].items() for a in [cid, *w["aliases"]]}
        self.workflows = wf["workflows"]

    def tier(self, component: str) -> int:
        # Unknown component => treat as Tier 0. Fail closed: an uncatalogued component must not be cheaper to ship.
        return self.components.get(component, {}).get("tier", 0)

    def owner(self, component: str) -> str | None:
        return self.components.get(component, {}).get("owner")

    def canonical_workflow(self, name: str | None) -> str | None:
        return self._alias.get(name or "")

    def controls_of(self, name: str | None) -> list[str]:
        cid = self.canonical_workflow(name)
        return self.workflows[cid]["controls"] if cid else []
