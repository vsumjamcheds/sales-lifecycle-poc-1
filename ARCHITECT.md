# Intelligent HCP Engagement POC — Architecture

## Closed loop

`Identity → Scout → Capacity → Strategist → Compliance → Scribe → Brain (SQL + Vector) → repeat`

- **Identity**: Active rep (`RepGA`, `RepNJ`, `RepFL`) scopes every query (territory = rep’s region).
- **Scout**: Ranks HCPs using **days 1–7 vs days 8–14** prescribing volume and interaction sentiment/recency.
- **Capacity**: Re-ranks Scout output using `weekly_visit_cap`, `RepCommitment`, and friction.
- **Strategist**: Claude + tool loop; retrieves **Chroma** `hcp_memory` for the HCP.
- **Compliance**: Same embedding model as memory; **Claims Master** in Chroma; similarity &lt; threshold → redline; off-label keywords → `BLOCK`.
- **Scribe**: PII scrub → summary + objections/tasks → new vectors in `hcp_memory` + optional `InteractionHistory` row.
- **Audit**: Full prompt, tool steps, gatekeeper before/after, accept/reject (SQLite `audit_logs`).

## Canonical data

| Store | Holds |
|--------|--------|
| SQLite | Reps, HCPs, prescribing signals, interactions, commitments, audit |
| Chroma `hcp_memory` | Unstructured interaction memory (per HCP, metadata filter) |
| Chroma `claims_master` | Approved claim phrases for gatekeeper |

## Run locally

Use the **project venv** for every command (system `python3` will not have `faker` etc.).

1. `python3 -m venv .venv && source .venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` → `.env`, set `ANTHROPIC_API_KEY`
4. `python -m src.scripts.seed_data` (or `.venv/bin/python -m src.scripts.seed_data` without activating)
5. Terminal A: `uvicorn src.api.main:app --reload --port 8000`
6. Terminal B: `streamlit run src/ui/app.py`
