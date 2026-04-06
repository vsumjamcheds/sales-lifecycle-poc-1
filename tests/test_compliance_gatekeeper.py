from __future__ import annotations

from src.agents.compliance_gatekeeper import evaluate_plan_text


def test_block_off_label_phrase():
    out = evaluate_plan_text("We should promote this device for an off-label pediatric use immediately.")
    assert out["status"] == "BLOCK"
