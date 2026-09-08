from . import models
from .database import SessionLocal

# Canonical test fixture (see CLAUDE.md) — kept consistent across the deck,
# prototype, and specs rather than inventing new synthetic data.
CANONICAL_PROJECT_NAME = "Acme Field Ops Case Management"


def seed_canonical_project() -> None:
    db = SessionLocal()
    try:
        exists = (
            db.query(models.Project)
            .filter(models.Project.name == CANONICAL_PROJECT_NAME)
            .first()
        )
        if not exists:
            db.add(
                models.Project(
                    name=CANONICAL_PROJECT_NAME,
                    target_platform="d365",
                    status="draft",
                )
            )
            db.commit()
    finally:
        db.close()
