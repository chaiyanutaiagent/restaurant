"""Two-step counter flow requires explicit server configuration, never a client flag."""
import uuid
from sqlalchemy import text


def configured_counter_mode(theme: object, branch_id: uuid.UUID | None) -> bool:
    if not isinstance(theme, dict) or branch_id is None:
        return False
    modes = theme.get("takeaway_branch_fulfillment_modes")
    mode = modes.get(str(branch_id)) if isinstance(modes, dict) else None
    if mode is None:
        mode = theme.get("takeaway_fulfillment_mode")
    return mode == "counter_combined"


async def counter_mode_enabled(db, company_id, brand_id, branch_id) -> bool:
    if not brand_id or not branch_id:
        return False
    theme = await db.scalar(text("SELECT theme_config FROM brands WHERE id=:brand_id AND company_id=:company_id AND is_active=true"),
        {"brand_id": brand_id, "company_id": company_id})
    return configured_counter_mode(theme, branch_id)
