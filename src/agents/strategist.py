from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.auth.context import RepContext
from src.database.audit_logger import log_event
from src.llm.claude_client import get_client, model_name
from src.tools.hcp_tools import fetch_hcp_performance, search_hcp_memory_tool


TOOL_DEFS = [
    {
        "name": "fetch_hcp_performance",
        "description": "Load prescribing volumes (days 1-7 vs 8-14) and recent interactions for an HCP in the rep's territory.",
        "input_schema": {
            "type": "object",
            "properties": {"hcp_id": {"type": "integer", "description": "HCP identifier"}},
            "required": ["hcp_id"],
        },
    },
    {
        "name": "search_hcp_memory",
        "description": "Semantic search in unstructured HCP memory for objections, preferences, and past discussion themes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hcp_id": {"type": "integer"},
                "query": {"type": "string"},
            },
            "required": ["hcp_id", "query"],
        },
    },
]


def run_strategist(db: Session, ctx: RepContext, hcp_id: int) -> dict[str, Any]:
    client = get_client()
    system = (
        "You are a med-tech field strategist. Propose exactly 3 concrete next steps for the upcoming engagement. "
        "Use tools to ground recommendations in data. When finished with tools, reply with JSON only: "
        '{"step_1":"...","step_2":"...","step_3":"..."} '
        "No off-label or unapproved claims."
    )
    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": f"Rep {ctx.code} territory {ctx.territory_code}. Build a 3-step pre-call plan for HCP id {hcp_id}.",
        }
    ]
    thought_log: list[str] = []

    for _ in range(8):
        resp = client.messages.create(
            model=model_name(),
            max_tokens=2048,
            system=system,
            tools=TOOL_DEFS,
            messages=messages,
        )
        thought_log.append(f"stop_reason={resp.stop_reason}")

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            tool_payloads: list[dict[str, Any]] = []
            for block in resp.content:
                if block.type != "tool_use":
                    continue
                name = block.name
                args = block.input if isinstance(block.input, dict) else {}
                thought_log.append(f"tool_call {name} {args}")
                if name == "fetch_hcp_performance":
                    out = fetch_hcp_performance(db, ctx, int(args.get("hcp_id", hcp_id)))
                elif name == "search_hcp_memory":
                    out = search_hcp_memory_tool(
                        int(args.get("hcp_id", hcp_id)),
                        str(args.get("query", "objections workflow training")),
                    )
                else:
                    out = {"error": "unknown tool"}
                tool_payloads.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, default=str),
                    }
                )
            messages.append({"role": "user", "content": tool_payloads})
            continue

        text = "".join(b.text for b in resp.content if b.type == "text")
        plan = _parse_plan_json(text)
        log_event(
            db,
            rep_code=ctx.code,
            event_type="strategist_complete",
            payload={"hcp_id": hcp_id, "thought_log": thought_log, "raw_text": text},
        )
        return {"plan": plan, "thought_log": thought_log, "raw_text": text}

    raise RuntimeError("Strategist tool loop exceeded iteration budget")


def _parse_plan_json(text: str) -> dict[str, str]:
    text = text.strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        obj = json.loads(text[start:end])
        return {
            "step_1": str(obj.get("step_1", "Review latest prescribing trend")),
            "step_2": str(obj.get("step_2", "Confirm clinical workflow fit")),
            "step_3": str(obj.get("step_3", "Offer training resources")),
        }
    except (ValueError, json.JSONDecodeError):
        return {
            "step_1": "Review HCP performance summary",
            "step_2": "Align messaging to approved indications",
            "step_3": "Schedule follow-up with clinical support",
        }
