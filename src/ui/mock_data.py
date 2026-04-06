"""Static mock JSON for offline UI preview (5 HCPs, 3-step plan)."""

SCOUT_REPORT_MOCK = [
    {
        "hcp_id": 101,
        "display_name": "Dr. Avery Chen",
        "specialty": "Cardiology",
        "priority_score": 2.41,
        "drivers": ["prescribing volume lower in days 8-14 vs 1-7", "fewer touches in second week"],
        "rank": 1,
    },
    {
        "hcp_id": 102,
        "display_name": "Dr. Jordan Lee",
        "specialty": "Orthopedics",
        "priority_score": 1.95,
        "drivers": ["negative sentiment increased in second week"],
        "rank": 2,
    },
    {
        "hcp_id": 103,
        "display_name": "Dr. Sam Rivera",
        "specialty": "Neurology",
        "priority_score": 1.72,
        "drivers": ["stable vs baseline window; monitor"],
        "rank": 3,
    },
    {
        "hcp_id": 104,
        "display_name": "Dr. Morgan Patel",
        "specialty": "Primary Care",
        "priority_score": 1.1,
        "drivers": ["prescribing volume lower in days 8-14 vs 1-7"],
        "rank": 4,
    },
    {
        "hcp_id": 105,
        "display_name": "Dr. Riley Brooks",
        "specialty": "Primary Care",
        "priority_score": 0.88,
        "drivers": ["stable vs baseline window; monitor"],
        "rank": 5,
    },
]

STRATEGIST_PLAN_MOCK = {
    "step_1": "Open with IFU-indicated outcomes and confirm current workflow constraints.",
    "step_2": "Offer standardized in-service training for clinical staff.",
    "step_3": "Align follow-up on training completion and adoption metrics.",
}

REP_OPTIONS = ["RepGA", "RepNJ", "RepFL"]


def mock_capacity_rows_for_rep(rep_code: str) -> list[dict]:
    """Offline preview: different IDs/names per rep so the top list visibly changes."""
    terr = rep_code.replace("Rep", "")
    base_id = {"RepGA": 9001, "RepNJ": 9101, "RepFL": 9201}.get(rep_code, 9001)
    out: list[dict] = []
    for i, row in enumerate(SCOUT_REPORT_MOCK):
        r = dict(row)
        r["hcp_id"] = base_id + i
        r["display_name"] = f"{row['display_name']} ({terr})"
        r["capacity_adjusted_score"] = row["priority_score"] - (i * 0.01)
        r["capacity_reason"] = f"mock · {terr}"
        out.append(r)
    return out
