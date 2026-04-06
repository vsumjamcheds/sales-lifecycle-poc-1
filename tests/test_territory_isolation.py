from __future__ import annotations

from src.database.audit_logger import log_event


def test_rep_ga_cannot_see_nj_hcps(client):
    r = client.get("/api/v1/hcps", headers={"X-Rep-Code": "RepGA"})
    assert r.status_code == 200
    data = r.json()
    assert all(h["territory_code"] == "GA" for h in data)
    ids = {h["display_name"] for h in data}
    assert "Dr. NJ One" not in ids


def test_rep_nj_only_nj(client):
    r = client.get("/api/v1/hcps", headers={"X-Rep-Code": "RepNJ"})
    assert r.status_code == 200
    data = r.json()
    assert all(h["territory_code"] == "NJ" for h in data)
    assert len(data) == 1


def test_plan_rejects_foreign_territory_hcp(client):
    # NJ-only HCP id is 5 with conftest seed order (reps 1-2, GA HCPs 3-4, NJ HCP 5)
    r = client.post("/api/v1/plan", headers={"X-Rep-Code": "RepGA"}, json={"hcp_id": 5})
    assert r.status_code == 200
    body = r.json()
    assert body.get("error") == "HCP not in territory"


def test_audit_logs_filtered_by_hcp_id(client, db_session):
    log_event(db_session, rep_code="RepGA", event_type="plan_requested", payload={"hcp_id": 3})
    log_event(db_session, rep_code="RepGA", event_type="scribe_sync", payload={"hcp_id": 99})
    r_all = client.get("/api/v1/audit-logs", headers={"X-Rep-Code": "RepGA"}, params={"limit": 50})
    assert r_all.status_code == 200
    assert len(r_all.json()) == 2
    r_f = client.get("/api/v1/audit-logs", headers={"X-Rep-Code": "RepGA"}, params={"limit": 50, "hcp_id": 3})
    assert r_f.status_code == 200
    data = r_f.json()
    assert len(data) == 1
    assert data[0]["payload"]["hcp_id"] == 3
