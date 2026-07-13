# SPDX-License-Identifier: CC-BY-SA-4.0
import asyncio
from typing import Any, Optional
from uuid import UUID


class RealtimeNotifier:
    """Mantiene un set di connessioni WebSocket e notifica in broadcast
    tutti i client connessi al cambio di stato di assignment o activity.
    """

    def __init__(self) -> None:
        self._connected: set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, conn: Any) -> None:
        self._connected.add(conn)

    async def disconnect(self, conn: Any) -> None:
        self._connected.discard(conn)

    async def broadcast(self, event: str, data: dict) -> None:
        for conn in list(self._connected):
            try:
                await conn.send_json({"event": event, "data": data})
            except Exception:
                self._connected.discard(conn)

    async def on_assignment_status_change(
        self, assignment_id: UUID, new_status: str
    ) -> None:
        await self.broadcast(
            "assignment_status",
            {"assignment_id": str(assignment_id), "status": new_status},
        )

    async def on_activity_status_change(
        self, activity_id: UUID, new_status: str
    ) -> None:
        await self.broadcast(
            "activity_status",
            {"activity_id": str(activity_id), "status": new_status},
        )

    def handle_outbox_event(self, event_type: str, payload: dict) -> None:
        """Bridge thread-safe tra il dispatcher outbox e il loop Quart."""
        if self._loop is None or self._loop.is_closed():
            return
        if event_type == "AssignmentStatusChanged":
            future = asyncio.run_coroutine_threadsafe(
                self.on_assignment_status_change(
                    UUID(payload["assignment_id"]), payload["new_status"]
                ),
                self._loop,
            )
        elif event_type == "ActivityStatusChanged":
            future = asyncio.run_coroutine_threadsafe(
                self.on_activity_status_change(
                    UUID(payload["activity_id"]), payload["new_status"]
                ),
                self._loop,
            )
        else:
            return
        # L'eccezione viene gestita internamente da broadcast; evitare warning
        # qualora il loop venga fermato mentre il worker è in esecuzione.
        future.add_done_callback(lambda completed: completed.exception() if not completed.cancelled() else None)
