from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from app.services.platform_reference_projection import process_projection_batch


logger = logging.getLogger(__name__)


@dataclass
class ReferenceProjectorRuntimeState:
    running: bool = False
    batches: int = 0
    claimed: int = 0
    applied: int = 0
    replayed: int = 0
    failed: int = 0
    loop_errors: int = 0
    last_error_type: str | None = None


reference_projector_state = ReferenceProjectorRuntimeState()


async def _wait_for_stop(stop_event: asyncio.Event, delay_seconds: float) -> None:
    if delay_seconds <= 0:
        await asyncio.sleep(0)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=delay_seconds)
    except TimeoutError:
        pass


async def run_reference_projector(
    stop_event: asyncio.Event,
    *,
    poll_seconds: float,
    batch_size: int,
    state: ReferenceProjectorRuntimeState = reference_projector_state,
) -> None:
    state.running = True
    state.last_error_type = None
    try:
        while not stop_event.is_set():
            delay_seconds = poll_seconds
            try:
                result = await process_projection_batch(limit=batch_size)
                state.batches += 1
                state.claimed += result.claimed
                state.applied += result.applied
                state.replayed += result.replayed
                state.failed += result.failed
                if result.failed:
                    state.last_error_type = "projection_event_failure"
                elif result.claimed:
                    state.last_error_type = None
                if result.claimed == batch_size and result.failed == 0:
                    delay_seconds = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - runtime dependency failure path
                state.loop_errors += 1
                state.last_error_type = f"{type(exc).__module__}.{type(exc).__name__}"
                logger.error("Reference projector loop failed: %s", state.last_error_type)
            await _wait_for_stop(stop_event, delay_seconds)
    finally:
        state.running = False
