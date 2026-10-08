import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agentic_gate import audit  # noqa: E402
from agentic_gate.catalog import ROOT, Policy  # noqa: E402
from agentic_gate.gate import evaluate  # noqa: E402
from agentic_gate.judge import KeywordJudge, calibrate  # noqa: E402

P = Policy()


def fx(name):
    return json.loads((ROOT / "fixtures" / name).read_text())


def failing(v):
    return {r.id for r in v.results if r.status == "fail"}


class Rules(unittest.TestCase):
    def test_t0_llm_only_is_blocked_on_owner_test_ops(self):
        v = evaluate(fx("01_t0_routing_llm_only.json"), P)
        self.assertEqual(v.verdict, "BLOCK")
        self.assertTrue({"OWN-001", "TEST-001", "OPS-001"} <= failing(v))

    def test_bot_approval_never_satisfies_owner(self):
        m = fx("01_t0_routing_llm_only.json")
        m["approvals"] = ["claude-review-bot", "@payments-core-bot"]
        self.assertIn("OWN-001", failing(evaluate(m, P)))
        m["approvals"] = ["@payments-core"]
        self.assertNotIn("OWN-001", failing(evaluate(m, P)))

    def test_architecture_boundary(self):
        self.assertEqual(failing(evaluate(fx("02_t2_upsell_boundary.json"), P)), {"ARCH-001"})

    def test_clean_change_passes(self):
        self.assertEqual(evaluate(fx("03_t1_pricing_clean.json"), P).verdict, "PASS")

    def test_pan_and_token_log_blocked(self):
        self.assertEqual(failing(evaluate(fx("04_t0_pan_in_fixture.json"), P)), {"SEC-001", "SEC-002"})

    def test_non_luhn_digits_are_not_a_pan(self):
        m = fx("03_t1_pricing_clean.json")
        m["files"][0]["diff"] = "+ID = 1234567890123456\n"
        self.assertNotIn("SEC-001", failing(evaluate(m, P)))

    def test_missing_telemetry_warns_not_blocks(self):
        v = evaluate(fx("05_t2_clean_missing_telemetry.json"), P)
        self.assertEqual(v.verdict, "PASS_WITH_WARNINGS")

    def test_unknown_component_fails_closed_to_tier0(self):
        self.assertEqual(P.tier("Brand_New_Service"), 0)


class Waivers(unittest.TestCase):
    def test_waivable_rule_can_be_waived_and_is_recorded(self):
        w = {"rules": ["ARCH-001"], "reason": "INC-1 hotfix", "approver": "@guest-revenue-ui"}
        v = evaluate(fx("02_t2_upsell_boundary.json"), P, waive=w)
        self.assertEqual(v.verdict, "PASS_WITH_WAIVER")
        self.assertEqual(v.waiver["approver"], "@guest-revenue-ui")

    def test_security_rules_cannot_be_waived(self):
        w = {"rules": ["SEC-001", "SEC-002", "OWN-001"], "reason": "x", "approver": "y"}
        v = evaluate(fx("04_t0_pan_in_fixture.json"), P, waive=w)
        self.assertEqual(v.verdict, "BLOCK")


class JudgeAuthority(unittest.TestCase):
    def test_weak_judge_is_demoted_to_advisory(self):
        self.assertEqual(calibrate(KeywordJudge(), P).mode, "advisory")

    def test_advisory_judge_cannot_block(self):
        m = fx("03_t1_pricing_clean.json")
        m["files"][0]["diff"] += "+    # TODO: verify signature\n"
        v = evaluate(m, P, KeywordJudge())
        self.assertEqual(v.verdict, "PASS")
        self.assertTrue(v.judge_findings)

    def test_judge_cannot_rescue_a_block(self):
        v = evaluate(fx("01_t0_routing_llm_only.json"), P, KeywordJudge())
        self.assertEqual(v.verdict, "BLOCK")

    def test_calibrated_judge_may_block_tier2_only(self):
        import agentic_gate.gate as g
        orig = g.calibrate
        g.calibrate = lambda j, p: type("C", (), {"mode": "blocking"})()  # pretend it passed calibration
        try:
            t2 = fx("05_t2_clean_missing_telemetry.json")
            t2["files"][0]["diff"] += "+    eval(x)\n"
            self.assertIn("JUDGE-001", failing(evaluate(t2, P, KeywordJudge())))
            t1 = fx("03_t1_pricing_clean.json")
            t1["files"][0]["diff"] += "+    eval(x)\n"
            self.assertNotIn("JUDGE-001", failing(evaluate(t1, P, KeywordJudge())))
        finally:
            g.calibrate = orig


class Audit(unittest.TestCase):
    def test_numbers_match_data_pack(self):
        s = audit.summarize(audit.load(), P)
        self.assertEqual((s["saved"], s["lost"], s["net_lost"]), (305, 585, 280))
        self.assertEqual(s["missing_time"], ["PR-038", "PR-041"])
        self.assertEqual((s["raw_labels"], s["canonical_labels"]), (4, 3))

    def test_no_pr_meets_required_controls(self):
        self.assertTrue(all(c["missing"] for c in audit.summarize(audit.load(), P)["coverage"]))

    def test_alias_collapse(self):
        self.assertEqual(P.canonical_workflow("agent-review"), P.canonical_workflow("ReviewAgent_v2"))


if __name__ == "__main__":
    unittest.main()
