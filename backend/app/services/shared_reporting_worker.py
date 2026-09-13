from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import (
    AsyncSessionLocal,
    PlatformSessionLocal,
    RestaurantSessionLocal,
    TakeawaySessionLocal,
    engine,
    restaurant_engine,
)
from app.services.shared_reporting_service import process_reporting_source_batch


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReportingSource:
    name: str
    kind: Literal["legacy", "takeaway"]
    session_factory: async_sessionmaker[AsyncSession]


@dataclass
class SharedReportingRuntimeState:
    running: bool = False
    batches: int = 0
    projected: int = 0
    replayed: int = 0
    failed: int = 0
    dead_lettered: int = 0
    loop_errors: int = 0
    last_error_type: str | None = None


shared_reporting_state = SharedReportingRuntimeState()


def configured_reporting_sources() -> list[ReportingSource]:
    sources = [ReportingSource("legacy_pos", "legacy", AsyncSessionLocal)]
    if restaurant_engine is not engine:
        sources.append(ReportingSource("restaurant_pos", "legacy", RestaurantSessionLocal))
    if settings.takeaway_feature_enabled and TakeawaySessionLocal is not None:
        sources.append(ReportingSource("takeaway_pos", "takeaway", TakeawaySessionLocal))
    return sources


async def _wait_for_stop(stop_event: asyncio.Event, delay_seconds: float) -> None:
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
    except TimeoutError:
        pass


async def run_shared_reporting_projector(
    stop_event: asyncio.Event,
    *,
    poll_seconds: float,
    batch_size: int,
    state: SharedReportingRuntimeState = shared_reporting_state,
) -> None:
    state.running = True
    state.last_error_type = None
    try:
        while not stop_event.is_set():
            immediate_retry = False
            try:
                for source in configured_reporting_sources():
                    async with source.session_factory() as source_db, PlatformSessionLocal() as platform_db:
                        result = await process_reporting_source_batch(
                            source_db,
                            platform_db,
                            source_stream=source.name,
                            source_kind=source.kind,
                            limit=batch_size,
                        )
                    state.batches += 1
                    state.projected += result.projected
                    state.replayed += result.replayed
                    state.failed += result.failed
                    state.dead_lettered += result.dead_lettered
                    immediate_retry = immediate_retry or (
                        result.discovered == batch_size and result.failed == 0
                    )
                state.last_error_type = None
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - runtime dependency failure path
                state.loop_errors += 1
                state.last_error_type = f"{type(exc).__module__}.{type(exc).__name__}"
                logger.error("Shared reporting projector loop failed: %s", state.last_error_type)
            await _wait_for_stop(stop_event, 0 if immediate_retry else poll_seconds)
    finally:
        state.running = False
