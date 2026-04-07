from __future__ import annotations

import os
import sys
from pathlib import Path

# Streamlit does not put the repo root on sys.path when running `streamlit run src/ui/app.py`.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
import streamlit as st
import streamlit.components.v1 as components

from src.ui.mock_data import REP_OPTIONS, STRATEGIST_PLAN_MOCK, mock_capacity_rows_for_rep

API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="HCP Engagement Command Center", layout="wide")

THEME_CSS = """
<style>
    /* Document + Streamlit shell: force light (Chrome honors this for scrollbars/menus) */
    :root, html, body {
        color-scheme: light !important;
    }
    html, body, .stApp, section[data-testid="stSidebar"],
    [data-testid="stAppViewContainer"], .main, section.main {
        scrollbar-width: thin !important;
        scrollbar-color: #8e8e98 #d4d4d8 !important;
    }
    /*
      Chrome/Blink: without -webkit-appearance:none, custom scrollbar rules are often ignored.
      Universal * so every overflow:auto region picks up grey bars.
    */
    *::-webkit-scrollbar {
        -webkit-appearance: none !important;
        appearance: none !important;
        width: 12px !important;
        height: 12px !important;
    }
    *::-webkit-scrollbar-track {
        background: #d4d4d8 !important;
        border-radius: 8px !important;
    }
    *::-webkit-scrollbar-thumb {
        background-color: #8e8e98 !important;
        border-radius: 8px !important;
        border: 3px solid #d4d4d8 !important;
        background-clip: padding-box !important;
    }
    *::-webkit-scrollbar-thumb:hover {
        background-color: #6b6b76 !important;
    }
    *::-webkit-scrollbar-corner {
        background: #d4d4d8 !important;
    }
    /* Select / dropdown panels (often render black in dark OS mode without theme base=light) */
    [data-baseweb="popover"], [data-baseweb="menu"], div[role="listbox"] {
        background-color: #e4e4e7 !important;
        color: #18181b !important;
    }
    ul[role="listbox"], li[role="option"] {
        background-color: #e4e4e7 !important;
        color: #18181b !important;
    }
    li[role="option"]:hover, li[role="option"][aria-selected="true"] {
        background-color: #d4d4d8 !important;
    }
    html, body, .stApp {
        background-color: #d4d4d8 !important;
        color: #18181b !important;
    }
    .main .block-container {
        background-color: #d4d4d8 !important;
        color: #18181b !important;
    }
    section[data-testid="stSidebar"] {
        background-color: #c4c4cc !important;
        border-right: 1px solid #a1a1aa !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: #18181b !important;
    }
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] span {
        color: #18181b !important;
    }
    .badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 12px;
        border: 1px solid #2563eb;
        color: #1d4ed8;
        background-color: #e0e7ff;
    }
    .verified { color: #15803d !important; font-weight: 600; }
    .blocked { color: #b91c1c !important; font-weight: 600; }
    .redline { color: #a16207 !important; font-weight: 600; }
</style>
"""
st.markdown(THEME_CSS, unsafe_allow_html=True)

# Widget-bound rep (avoid index=session rep_code — that resets the selectbox on rerun)
if "active_rep" not in st.session_state:
    st.session_state.active_rep = st.session_state.pop("rep_code", "RepGA")
if "thought_log" not in st.session_state:
    st.session_state.thought_log = []
if "compliance" not in st.session_state:
    st.session_state.compliance = None
if "plan" not in st.session_state:
    st.session_state.plan = None
if "scout_rows" not in st.session_state:
    st.session_state.scout_rows = []


def api_headers() -> dict[str, str]:
    return {"X-Rep-Code": st.session_state.active_rep}


def fetch_json(method: str, path: str, **kwargs):
    try:
        hdrs = {**api_headers(), "Cache-Control": "no-cache", "Pragma": "no-cache"}
        with httpx.Client(timeout=120.0) as client:
            r = client.request(method, f"{API_BASE}{path}", headers=hdrs, **kwargs)
            if r.status_code >= 400:
                return None, r.text
            return r.json(), None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def _api_connection_hint(err: str | None) -> str:
    if not err:
        return ""
    e = str(err).lower()
    if "connection refused" in e or "errno 61" in e or "actively refused" in e:
        return (
            f"\n\n**Fix:** start the API in another terminal from the project root:\n\n"
            f"`uvicorn src.api.main:app --port 8000`\n\n"
            f"Streamlit is calling **`{API_BASE}`** (set `API_BASE_URL` in `.env` if the API runs elsewhere)."
        )
    return ""


def _audit_entry_hcp_id(entry: dict) -> int | None:
    p = entry.get("payload")
    if not isinstance(p, dict):
        return None
    v = p.get("hcp_id")
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _audit_logs_for_hcp_display(raw: list | None, hcp_id: int) -> list:
    """Drop any rows not tied to this HCP (stale session cache or pre-filter API)."""
    if not raw:
        return []
    hid = int(hcp_id)
    return [e for e in raw if isinstance(e, dict) and _audit_entry_hcp_id(e) == hid]


def _field_note_widget_key(rep: str, hcp_id: object) -> str:
    """Composite key so Streamlit treats the text area as new when rep/HCP/refresh scope changes."""
    v = int(st.session_state.get("_scribe_reset_v", 0))
    return f"scribe_field__{rep}__{hcp_id}__{v}"


def _strategist_thought_digest(logs: list) -> tuple[str, str]:
    """Two short lines for reps; derived from API thought_log (post-hoc, accurate)."""
    if not logs:
        return ("", "")
    tool_names: list[str] = []
    rounds = 0
    for ln in logs:
        if not isinstance(ln, str):
            continue
        if ln.startswith("stop_reason="):
            rounds += 1
        elif ln.startswith("tool_call "):
            rest = ln[len("tool_call ") :].strip()
            name = rest.split(" ", 1)[0] if rest else ""
            if name and name not in tool_names:
                tool_names.append(name)
    labels = {
        "fetch_hcp_performance": "prescribing & visit history",
        "search_hcp_memory": "semantic memory search",
    }
    shown = [labels.get(n, n) for n in tool_names]
    line1 = (
        f"Strategist finished **{rounds}** model round(s)"
        + (f" and used **{len(tool_names)}** tool type(s)." if tool_names else " (no tools in log).")
    )
    if shown:
        line2 = "**Grounding:** " + "; ".join(shown) + "."
    elif any(isinstance(ln, str) and "mock" in ln.lower() for ln in logs):
        line2 = "**Grounding:** mock data — enable live API for real tool traces."
    else:
        line2 = "**Grounding:** plan text only (no tool calls in this run)."
    return (line1, line2)


def _clear_engagement_state() -> None:
    st.session_state["_scroll_main_top"] = True
    st.session_state.pop("selected_hcp_id", None)
    st.session_state.pop("plan", None)
    st.session_state.pop("compliance", None)
    st.session_state.thought_log = []
    st.session_state.pop("audit_logs_data", None)
    st.session_state.pop("audit_logs_error", None)
    st.session_state.pop("audit_logs_scope_hcp_id", None)
    # Force main block to reset HCP list + picker for the new rep
    st.session_state.pop("_last_hcp_list_rep", None)


with st.sidebar:
    st.markdown("### Territory context")
    st.selectbox(
        "Active rep",
        REP_OPTIONS,
        key="active_rep",
        on_change=_clear_engagement_state,
    )
    st.caption("Data scope follows `X-Rep-Code` to the API.")
    use_live = st.toggle("Use live API", value=True)
    if st.button("Refresh data"):
        st.session_state.pop("scout_rows", None)
        st.session_state.pop("_last_hcp_list_rep", None)
        st.session_state["_scribe_reset_v"] = int(st.session_state.get("_scribe_reset_v", 0)) + 1
        _clear_engagement_state()
        st.rerun()

# After rep change: scroll main Command Center pane to top (Streamlit keeps prior scroll offset on rerun).
if st.session_state.pop("_scroll_main_top", False):
    components.html(
        """
        <script>
        (function () {
          function go() {
            try {
              var d = window.parent.document;
              var nodes = d.querySelectorAll(
                'section.main, [data-testid="stAppViewContainer"], .stMain, .main .block-container'
              );
              nodes.forEach(function (el) { el.scrollTop = 0; });
              d.documentElement.scrollTop = 0;
              d.body.scrollTop = 0;
            } catch (e) {}
          }
          setTimeout(go, 0);
          setTimeout(go, 50);
        })();
        </script>
        """,
        height=0,
        width=0,
    )

rows: list = []
if use_live:
    data, err = fetch_json(
        "GET",
        f"/api/v1/capacity?rep_scope={st.session_state.active_rep}",
    )
    if data:
        rows = data.get("hcps", [])
        st.session_state.scout_rows = rows
    else:
        st.warning(f"API unavailable ({err}). Showing mock.{_api_connection_hint(err)}")
        rows = mock_capacity_rows_for_rep(st.session_state.active_rep)
else:
    rows = mock_capacity_rows_for_rep(st.session_state.active_rep)

st.markdown("## 1 · HCP priority")
st.caption(
    f"Territory: **{st.session_state.active_rep}** — pick one HCP; engagement updates below."
)

if not rows:
    st.error("No HCPs in this territory. Try another rep or **Refresh data**.")
    st.stop()


def _hcp_option_label(r: dict) -> str:
    score = r.get("capacity_adjusted_score", r.get("priority_score", 0))
    badge = "P1" if r.get("rank", 99) <= 2 else "P2"
    drivers = "; ".join(r.get("drivers", [])[:1]) or r.get("capacity_reason", "")
    return (
        f"[{badge}] {r.get('display_name')} · ID {r.get('hcp_id')} · "
        f"score {score:.2f} · {r.get('specialty', '')} — {drivers[:80]}"
    )


_pick_key = f"hcp_priority_idx_{st.session_state.active_rep}"
# When rep changes, reset picker index so labels/options always match `rows` for this rep
if st.session_state.get("_last_hcp_list_rep") != st.session_state.active_rep:
    st.session_state["_last_hcp_list_rep"] = st.session_state.active_rep
    st.session_state[_pick_key] = 0
elif _pick_key not in st.session_state:
    st.session_state[_pick_key] = 0
if st.session_state[_pick_key] >= len(rows):
    st.session_state[_pick_key] = 0


def _on_hcp_pick_change() -> None:
    st.session_state.pop("plan", None)
    st.session_state.pop("compliance", None)
    st.session_state.thought_log = []
    st.session_state.pop("audit_logs_data", None)
    st.session_state.pop("audit_logs_error", None)
    st.session_state.pop("audit_logs_scope_hcp_id", None)


st.selectbox(
    "Select HCP (ranked)",
    options=list(range(len(rows))),
    format_func=lambda i: _hcp_option_label(rows[i]),
    key=_pick_key,
    on_change=_on_hcp_pick_change,
)

picked_idx = int(st.session_state[_pick_key])
sel_row = rows[picked_idx]
hcp_id = sel_row.get("hcp_id")
st.session_state.selected_hcp_id = hcp_id
focused_name = sel_row.get("display_name")

# After Scribe sync: refetch this HCP’s audit trail (needs hcp_id from selection).
if (
    st.session_state.pop("_refresh_audit_on_next_run", False)
    and use_live
    and hcp_id is not None
):
    _path = f"/api/v1/audit-logs?limit=100&hcp_id={int(hcp_id)}"
    _ad, _ae = fetch_json("GET", _path)
    if _ad is not None:
        st.session_state.audit_logs_data = _ad
        st.session_state.audit_logs_scope_hcp_id = int(hcp_id)
        st.session_state.pop("audit_logs_error", None)
    else:
        st.session_state.audit_logs_data = None
        st.session_state.audit_logs_error = _ae

with st.expander("Scout / capacity detail for selected HCP", expanded=False):
    st.write(f"**Drivers:** {'; '.join(sel_row.get('drivers', [])) or sel_row.get('capacity_reason', '—')}")
    st.json(
        {
            "rank": sel_row.get("rank"),
            "priority_score": sel_row.get("priority_score"),
            "capacity_adjusted_score": sel_row.get("capacity_adjusted_score"),
            "capacity_reason": sel_row.get("capacity_reason"),
            "feasible_this_week": sel_row.get("feasible_this_week"),
        }
    )

st.divider()

st.markdown("## 2 · Engagement Command Center")
st.write(f"**Working on:** {focused_name} · **ID:** `{hcp_id}`")
st.caption("Pre-call: generate a plan first. Post-call: capture notes below.")

st.markdown("#### Pre-call · Strategist + Compliance")
st.caption(
    "**What runs when you generate a plan** · "
    "(1) Strategist calls the model with your territory context. "
    "(2) It may pull **HCP performance** (prescribing and visits) and **search memory** (past notes in the vector store). "
    "(3) It returns three concrete pre-call steps. "
    "(4) **Compliance** checks wording against approved claims and may verify, redline, or block."
)
if st.button("Generate plan (Strategist + Compliance)") and hcp_id:
    if use_live:
        with st.spinner("Strategist is gathering data and drafting steps; then compliance reviews wording…"):
            payload, err = fetch_json("POST", "/api/v1/plan", json={"hcp_id": int(hcp_id)})
        if payload:
            st.session_state.plan = payload.get("strategist", {}).get("plan")
            st.session_state.thought_log = payload.get("strategist", {}).get("thought_log", [])
            st.session_state.compliance = payload.get("compliance")
            st.session_state["_expand_thought_after_plan"] = True
        else:
            st.error(f"{err}{_api_connection_hint(err)}")
    else:
        st.session_state.plan = STRATEGIST_PLAN_MOCK
        st.session_state.thought_log = ["mock: no API"]
        st.session_state.compliance = {
            "status": "VERIFIED",
            "final_text": "\n".join(STRATEGIST_PLAN_MOCK.values()),
            "citation": {"claim_id": "claim_training", "approved_text": "training and in-service"},
            "similarity": 0.94,
        }
        st.session_state["_expand_thought_after_plan"] = True

plan = st.session_state.plan
comp = st.session_state.compliance

if plan:
    st.markdown("#### Suggested actions")
    st.write(f"1. {plan.get('step_1')}")
    st.write(f"2. {plan.get('step_2')}")
    st.write(f"3. {plan.get('step_3')}")

if comp:
    status = comp.get("status", "")
    if status == "VERIFIED":
        st.markdown('<p class="verified">Verified — aligned with approved claims</p>', unsafe_allow_html=True)
        cit = comp.get("citation") or {}
        st.markdown(f"**Citation:** `{cit.get('claim_id','')}` — {cit.get('approved_text','')}")
    elif status == "REDLINE":
        st.markdown('<p class="redline">Redlined — substituted approved phrasing</p>', unsafe_allow_html=True)
        st.write(comp.get("final_text", ""))
        cit = comp.get("citation") or {}
        with st.popover("View citation"):
            st.write(cit.get("approved_text", ""))
    elif status == "BLOCK":
        st.markdown('<p class="blocked">Blocked — policy violation</p>', unsafe_allow_html=True)
        st.error(comp.get("reason", "Blocked"))

    dec = st.radio("Decision", ["accept", "reject"], horizontal=True)
    if st.button("Log decision") and use_live:
        fetch_json(
            "POST",
            "/api/v1/decision",
            json={"decision": dec, "payload": {"hcp_id": hcp_id, "compliance_status": status}},
        )
        st.success("Decision logged to audit trail.")

_expand_thought = bool(st.session_state.pop("_expand_thought_after_plan", False))
_thought_lines = st.session_state.thought_log
if _thought_lines:
    d1, d2 = _strategist_thought_digest(_thought_lines)
    if d1:
        st.markdown(f"**How this plan was built**  \n{d1}  \n{d2}")

with st.expander("Agent thought process (full log)", expanded=_expand_thought):
    if not _thought_lines:
        st.caption("Generate a plan to see model stops and tool calls here.")
    for line in _thought_lines:
        st.text(line)

st.divider()
st.markdown("#### Post-call · Scribe")
_field_key = _field_note_widget_key(st.session_state.active_rep, hcp_id)
st.caption(
    "Draft text stays in this browser tab until **Sync to Brain**. "
    "After sync, the API stores a scrubbed copy, Chroma memory, an interaction row, and an audit entry "
    "for this HCP (see **Conversation audit trail** below)."
)
note = st.text_area(
    "Field note",
    height=140,
    placeholder="Capture discussion themes, objections, next steps…",
    key=_field_key,
)
if st.button("Sync to Brain") and hcp_id and note.strip():
    if use_live:
        out, err = fetch_json("POST", "/api/v1/scribe", json={"hcp_id": int(hcp_id), "note": note.strip()})
        if out:
            st.success("Synced — memory and timeline updated.")
            st.json(out.get("parsed", {}))
            st.session_state.thought_log.append("scribe: note ingested")
            st.session_state.pop(_field_key, None)
            st.session_state["_refresh_audit_on_next_run"] = True
            st.rerun()
        else:
            st.error(f"{err}{_api_connection_hint(err)}")
    else:
        st.info("Mock mode: enable live API to persist.")

st.divider()
st.markdown("### Conversation audit trail")
st.caption(
    f"Audit events for **{focused_name}** · HCP `{hcp_id}` · rep **{st.session_state.active_rep}** "
    "(plans, compliance, decisions, scribe syncs tied to this customer)."
)
if not use_live:
    st.caption("Turn on **Use live API** to load the trail from the API.")
elif hcp_id is None:
    st.warning("Select an HCP above to load audit events.")
else:
    _hcp_audit = int(hcp_id)
    if st.session_state.get("audit_logs_scope_hcp_id") != _hcp_audit:
        st.session_state.pop("audit_logs_data", None)
        st.session_state.pop("audit_logs_error", None)
        st.session_state.pop("audit_logs_scope_hcp_id", None)

    _audit_path = f"/api/v1/audit-logs?limit=100&hcp_id={_hcp_audit}"
    if st.button("Load audit trail for this HCP"):
        _data, _err = fetch_json("GET", _audit_path)
        if _data is not None:
            st.session_state.audit_logs_data = _data
            st.session_state.audit_logs_scope_hcp_id = _hcp_audit
            st.session_state.pop("audit_logs_error", None)
        else:
            st.session_state.audit_logs_data = None
            st.session_state.audit_logs_error = _err
    err = st.session_state.get("audit_logs_error")
    if err:
        if "Not Found" in str(err) or "not found" in str(err).lower():
            st.error(
                f"**Audit API returned 404 (Not Found).** Example URL: `{API_BASE}{_audit_path}` "
                "with your rep header. Usually this means the **FastAPI process is old** (restart uvicorn) or "
                f"**API_BASE_URL** is wrong (currently `{API_BASE}` — must be the API, not Streamlit’s port). "
                f"Raw response: {err}"
            )
        else:
            st.error(str(err))
    raw_logs = st.session_state.get("audit_logs_data")
    logs = _audit_logs_for_hcp_display(raw_logs, _hcp_audit)
    if not err and raw_logs is None:
        st.info("Click **Load audit trail for this HCP** to fetch history for the selected customer.")
    elif not err and len(logs) == 0:
        st.info(f"No audit entries yet for this HCP (**{focused_name}**).")
    elif not err:
        if raw_logs is not None and len(logs) < len(raw_logs):
            st.caption("_Showing only events for this HCP; some cached rows were hidden._")
        st.caption(f"{len(logs)} entries (newest first).")
        for entry in logs:
            ts = entry.get("created_at") or "—"
            et = entry.get("event_type") or "—"
            eid = entry.get("id")
            with st.expander(f"{ts} · **{et}** · id {eid}", expanded=False):
                st.json(entry.get("payload") or {})
