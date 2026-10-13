"""Cross-system recipe proposals. Never used as the operational stock BOM."""
import uuid
from sqlalchemy import CheckConstraint, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.base import UUIDMixin, TimestampMixin

class RecipeReview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recipe_reviews"
    __table_args__ = (
        UniqueConstraint("company_id", "request_key", name="uq_recipe_reviews_request"),
        CheckConstraint("system IN ('restaurant','takeaway')", name="recipe_review_system"),
        CheckConstraint("status IN ('draft','submitted','returned','rejected','approved_hold','published')", name="recipe_review_status"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    system: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    # Frozen source evidence, editable proposal and append-only decision snapshots.
    baseline: Mapped[dict] = mapped_column(JSONB)
    proposal: Mapped[dict] = mapped_column(JSONB)
    history: Mapped[list] = mapped_column(JSONB, default=list)
    publication: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))


class RecipeLegacyRegistration(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "recipe_legacy_registrations"
    __table_args__ = (UniqueConstraint("company_id", "system", "source_id", name="uq_recipe_legacy_source"),)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    system: Mapped[str] = mapped_column(String(20))
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    registered_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class RecipeProductionRun(UUIDMixin, TimestampMixin, Base):
    """Durable outbox: shared raw stock commits once, output delivery may retry."""
    __tablename__ = "recipe_production_runs"
    __table_args__ = (
        UniqueConstraint("company_id", "request_key", name="uq_recipe_run_request"),
        CheckConstraint("status IN ('output_pending','completed')", name="recipe_run_status"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    brand_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    review_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(30))
    snapshot: Mapped[dict] = mapped_column(JSONB)
