# agentic-gate: engineering judgment as code (prototype)

Prototype for **Case B: Encoding Engineering Judgment** (Mews Guest Revenue Tribe, Staff Engineer).
It is deliberately small. It exists to make three claims from the deck concrete and runnable.

> Confidential: built from materials shared for this evaluation only. Keep this repository private.
> `data/deployments.csv` is the supplied data pack, included only so the audit can be reproduced.

## The idea in one paragraph

In the data pack, the controls a PR received were determined by **which agent the builder happened to run**, not by **how
risky the component is**. A Sev-1 on `Payment_Routing_Core` shipped behind the same single LLM review that a UI widget gets.
This prototype moves that decision into machine-readable policy: risk **tier belongs to the component**, **deterministic
gates are mandatory per tier**, and an **LLM judge is advisory until it earns authority** from a measured golden-set score.

## What it demonstrates (mapped to the brief)

| Brief question | What you can run | What it shows |
|---|---|---|
| 1. Root cause of friction and off-bar shipments | `make audit` | Net **+280 min lost** (305 saved vs 585 lost; the Sev-1 alone is 480). 4 workflow labels are really 3. 2 of 10 rows have no time data. **0/10** PRs received the controls their tier requires. |
| 2. Pattern to encode judgment so it is reliable *and* mandatory | `make demo`, `make calibrate` | Tiered policy-as-code gate; fixtures blocked/passed/warned with rule ids; non-waivable security rules; audited waiver recording; judge demoted to advisory because recall 0.6 < 0.8 bar. |
| 3. Adoption and deprecation of fragmented tooling | `out/events.jsonl` after `make demo` | One canonical telemetry event per run (canonical workflow id, policy hash, verdict, waivers). This is the adoption/deprecation dashboard data source. The plan itself is in the deck. |

## Run it

Python 3.9+, **standard library only**, nothing to install.

```bash
make audit        # re-analyse the data pack + control coverage replay
make demo         # gate 5 illustrative change manifests (3 blocked, 1 pass, 1 warn)
make calibrate    # measure the LLM-judge stand-in against evals/golden.json, approve evals/judge_authority.json
make test         # unit tests (also run in CI, see .github/workflows/ci.yml)
```

Gate a single manifest (exit code 1 on BLOCK, so it drops straight into CI as a required check):

```bash
python3 -m agentic_gate check fixtures/02_t2_upsell_boundary.json
# audited break-glass for a waivable rule:
python3 -m agentic_gate check fixtures/02_t2_upsell_boundary.json \
    --waive ARCH-001 --reason "INC-123 hotfix" --approver @guest-revenue-ui
```

## How it fits together

```
 policy/ (versioned, owned in one repo, hash pinned into every verdict)
   components.json  component -> tier, owner, import boundaries     (blast radius)
   rules.json       rule id -> tiers, block|warn, waivable?, why/fix
   controls.json    controls REQUIRED per tier
   workflows.json   canonical agent workflow ids + aliases + controls provided
        |
        v
 change manifest (files+diffs, approvals, rollout, workflow, time impact)
        |
        v
 gate.evaluate():  tier lookup -> applicable deterministic rules -> verdict
        |              unknown component => Tier 0 (fail closed)
        |              LLM judge: advisory by default; can only ADD a block, on Tier 2,
        |                         and only if golden-set precision & recall clear the bars
        v
 PASS | PASS_WITH_WARNINGS | PASS_WITH_WAIVER | BLOCK  ->  telemetry event (out/events.jsonl)
```

Design decisions worth defending:

- **Tier is a property of the component, not the tool.** Builders cannot choose a lighter control set by choosing a lighter agent.
- **Deterministic first.** Boundary, test, rollout, secrets and ownership checks give the same answer every run. An LLM reading a diff is not evidence behaviour is preserved.
- **Authority is earned and tier-limited.** The judge never overrides a block, never counts as an approver, and is never the sole control on Tier 0/1. `make calibrate` shows the mechanism: the naive judge catches syntactic smells but misses semantic bugs (non-idempotent retry, dropped cents), so it stays advisory.
- **Calibration is an offline, versioned step, not a per-PR cost.** `make calibrate` is run whenever the model/prompt/policy changes and writes an approved record to `evals/judge_authority.json` (judge name + policy hash + measured mode). `gate.evaluate()` only *reads* that record -- it never recalibrates during a gate run. A record that doesn't match the current judge or policy hash is stale and the gate fails closed to advisory. This matters once the judge is a real model: the authority decision should cost one lookup, not a fresh batch of model calls on every PR.
- **Humans accept risk; gates hunt for misses.** Tier 0 keeps a human CODEOWNER sign-off (`OWN-001`, non-waivable, model approvals ignored). This is a deliberate reading of "no manual review to catch architectural misses": the human no longer has to *find* problems, only to own the risk.
- **Mandatory means enforced centrally.** In production the gate runs as a required status check from CI/ruleset, not in a builder's local agent, so it cannot be skipped. Waivers exist but only for waivable rules and are always recorded with approver and reason. **In this prototype that is audited recording, not authorization**: `--approver` is any string the caller supplies, with no check that the string is a real person or has the authority to waive the rule. Production would enforce that via GitHub/team identity (e.g. the waive must come from a member of the component's CODEOWNERS team, recorded through the PR review itself rather than a free-text CLI flag).
- **Every incident and revert feeds the golden set**, so the evals tighten over time.

## Mapping to production (not built here)

| Prototype | Production |
|---|---|
| `policy/*.json` | YAML/Rego in a central policy repo (OPA/Conftest), CODEOWNERS on the catalog, versioned releases |
| `check` exit code | GitHub required status check via an org ruleset |
| change manifest | built in CI from the PR and diff (a GitHub App or Action) |
| `KeywordJudge` | model-backed judge with the same `review()` interface and the same calibration gate |
| `out/events.jsonl` | warehouse table feeding adoption and outcome dashboards |

## What I deliberately did not build

- **No real LLM calls.** The judge is an offline stand-in so the demo is deterministic and free. The interface and calibration logic are the real part.
- **No GitHub integration** (App, webhook, status check, diff ingestion). Manifests are hand-written JSON.
- **No policy UI, auth, database, or dashboard.** Policy is files, telemetry is JSONL.
- **No SAST/dependency scanning or full architecture analysis.** The checks are narrow, representative examples of the pattern, not a complete rule set.
- **No rollout machinery** (agent distribution, deprecation of the existing tools). The 3-month plan is in the deck.

## Caveats, stated plainly

- **n=10 is anecdotal.** The audit is directional, not statistical.
- **Fixtures are illustrative, not real diffs.** `fixtures/01` mirrors the *shape* of PR-042 (Tier 0, LLM-only review); it is not what that PR contained.
- **Workflow-to-controls mapping is inferred** from the workflow names (e.g. `Code_Gen_Assist` provides no review). It is in `policy/workflows.json` and must be confirmed with the team.
- **`agent-review` and `ReviewAgent_v2` are treated as the same workflow**; that is an assumption to verify.
- Tier assignments are my proposal from component names, to be confirmed with the owning teams.
- Regex checks (PAN, secrets, log scanning) will have false positives/negatives; production would use a vetted scanner.
- SEC-001 blocks published PSP sandbox test PANs too, not just real ones. `fixtures/04` deliberately commits the published Visa test number `4111 1111 1111 1111` literally in a test file to show this: the rule's remediation is to load sandbox test PANs from a fixture/env at run time, never to hardcode the digits in a diff, so there is no carve-out for "it's only a test number."

## Layout

```
agentic_gate/   catalog, checks, judge, gate, telemetry, audit, cli
policy/         tiers, rules, workflows, required controls
fixtures/       5 illustrative change manifests
evals/          golden.json (calibration cases) + judge_authority.json (approved calibration, see `make calibrate`)
data/           supplied data pack (CSV)
tests/          unittest suite
.github/        CI workflow running `make test` on every push/PR
```
