"""
Seed SQLite + Chroma with 14 days of data (days 1-7 vs 8-14) and 50 HCPs.
Run: python -m src.scripts.seed_data
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from faker import Faker

from src.database.models import (
    HCP,
    InteractionHistory,
    PrescribingSignal,
    Rep,
    RepCommitment,
)
from src.database.session import SessionLocal, init_db
from src.constants import ANCHOR_START
from src.database.vector_store import add_hcp_memory, seed_claims_phrases

fake = Faker()
Faker.seed(42)
random.seed(42)

DRUG_ID = "DEV-1001"

REPS = [
    ("RepGA", "GA", 12, 6, 0.15),
    ("RepNJ", "NJ", 10, 5, 0.25),
    ("RepFL", "FL", 11, 5, 0.20),
]


def _period_dates(period: str) -> list[date]:
    if period == "A":
        return [ANCHOR_START + timedelta(days=i) for i in range(7)]
    return [ANCHOR_START + timedelta(days=7 + i) for i in range(7)]


def run() -> None:
    init_db()
    db = SessionLocal()

    db.query(InteractionHistory).delete()
    db.query(PrescribingSignal).delete()
    db.query(RepCommitment).delete()
    db.query(HCP).delete()
    db.query(Rep).delete()
    db.commit()

    rep_rows: dict[str, Rep] = {}
    for code, terr, cap, new_t, friction in REPS:
        r = Rep(
            code=code,
            territory_code=terr,
            weekly_visit_cap=cap,
            max_new_targets_per_week=new_t,
            travel_friction_score=friction,
        )
        db.add(r)
        db.flush()
        rep_rows[code] = r

    territories = ["GA", "NJ", "FL"]
    hcps: list[HCP] = []
    for i in range(50):
        terr = territories[i % 3]
        h = HCP(
            display_name=fake.name(),
            specialty=random.choice(["Cardiology", "Orthopedics", "Neurology", "Primary Care"]),
            territory_code=terr,
        )
        db.add(h)
        db.flush()
        hcps.append(h)

    declining_ids = {h.id for h in random.sample(hcps, k=15)}

    for h in hcps:
        declining = h.id in declining_ids
        for d in _period_dates("A"):
            base = random.uniform(40, 90)
            vol = base + random.uniform(-5, 5)
            db.add(
                PrescribingSignal(
                    hcp_id=h.id,
                    drug_id=DRUG_ID,
                    signal_date=d,
                    volume=round(vol, 2),
                )
            )
        for d in _period_dates("B"):
            base = random.uniform(40, 90)
            if declining:
                vol = base * random.uniform(0.55, 0.85) + random.uniform(-4, 4)
            else:
                vol = base * random.uniform(0.95, 1.08) + random.uniform(-3, 3)
            db.add(
                PrescribingSignal(
                    hcp_id=h.id,
                    drug_id=DRUG_ID,
                    signal_date=d,
                    volume=max(5.0, round(vol, 2)),
                )
            )

    for h in hcps:
        rep = rep_rows[f"Rep{h.territory_code}"]
        for d in _period_dates("A"):
            if random.random() < 0.35:
                db.add(
                    InteractionHistory(
                        hcp_id=h.id,
                        rep_id=rep.id,
                        interaction_date=d,
                        interaction_type=random.choice(["visit", "call", "email"]),
                        sentiment=random.choice(["positive", "neutral", "negative"]),
                        objection=random.choice([None, None, "Cost concern", "Formulary"]) if random.random() < 0.3 else None,
                        notes=fake.sentence(nb_words=8),
                    )
                )
        for d in _period_dates("B"):
            touch_prob = 0.25 if h.id in declining_ids else 0.4
            if random.random() < touch_prob:
                sent = random.choice(["positive", "neutral", "negative", "negative"]) if h.id in declining_ids else random.choice(["positive", "neutral", "negative"])
                db.add(
                    InteractionHistory(
                        hcp_id=h.id,
                        rep_id=rep.id,
                        interaction_date=d,
                        interaction_type=random.choice(["visit", "call", "email"]),
                        sentiment=sent,
                        objection=random.choice(["Efficacy question", "Prior auth", None]) if random.random() < 0.35 else None,
                        notes=fake.sentence(nb_words=10),
                    )
                )

    week_start = ANCHOR_START + timedelta(days=7)
    for r in rep_rows.values():
        db.add(
            RepCommitment(
                rep_id=r.id,
                week_start=week_start,
                committed_visits=random.randint(3, 6),
                admin_blocks=random.randint(0, 2),
            )
        )

    db.commit()

    seed_claims_phrases(
        [
            (
                "claim_device_safety",
                "The device has demonstrated safety in the indicated patient population per the IFU.",
            ),
            (
                "claim_training",
                "Our team provides standardized training and in-service support for clinical staff.",
            ),
            (
                "claim_efficacy_indicated",
                "Clinical outcomes in the indicated use show improvement in mobility scores versus baseline in pivotal trials.",
            ),
            (
                "claim_not_offlabel",
                "Discuss only on-label indications and direct questions about unapproved uses to medical affairs.",
            ),
        ]
    )

    sample_mem = random.sample(hcps, k=min(12, len(hcps)))
    for h in sample_mem:
        add_hcp_memory(
            h.id,
            f"Prior touch: {fake.sentence(nb_words=14)} Interest in workflow integration.",
            source="seed",
        )

    db.close()
    print("Seeded reps, 50 HCPs, 14d signals & interactions, commitments, Chroma claims + sample memory.")


if __name__ == "__main__":
    run()
