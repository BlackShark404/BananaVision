"""Admission and draining for this station; hardware serialization remains separate."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import partial

from fastapi import HTTPException

station_lock = asyncio.Lock()
maintenance_context: ContextVar[bool] = ContextVar("maintenance_context", default=False)


async def finish_on_disconnect(awaitable):
    """Do not abandon file/DB promotion or power dispatch on HTTP disconnect."""
    task = asyncio.create_task(awaitable)
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    if cancelled:
        if not task.cancelled():
            task.exception()
        raise asyncio.CancelledError
    return task.result()


async def run_blocking(function, *args, **kwargs):
    """A cancelled caller still owns its hardware until the worker has finished."""
    worker = asyncio.create_task(asyncio.to_thread(partial(function, *args, **kwargs)))
    cancelled = False
    while not worker.done():
        try:
            await asyncio.shield(worker)
        except asyncio.CancelledError:
            cancelled = True
        except Exception:
            if cancelled:
                raise asyncio.CancelledError from None
            raise
    if cancelled:
        # Retrieve any exception so the abandoned worker never becomes an unobserved task.
        if not worker.cancelled():
            worker.exception()
        raise asyncio.CancelledError
    return worker.result()


class StationCoordinator:
    def __init__(self, drain_timeout: float = 120):
        self.state = "ready"
        self.kind: str | None = None
        self.active = 0
        self.drain_timeout = drain_timeout
        self._empty = asyncio.Event()
        self._empty.set()
        self._depth = ContextVar(f"station_depth_{id(self)}", default=0)
        self.database_barrier = None
        self.owner_check = None
        self.runtime_resume = None

    def assert_ready(self):
        if self.state != "ready":
            raise HTTPException(503, f"Station is {self.state}; new work is temporarily unavailable",
                                headers={"Retry-After": "5"})

    @asynccontextmanager
    async def operation(self):
        if self._depth.get():
            yield
            return
        self.assert_ready()
        self.active += 1
        self._empty.clear()
        token = self._depth.set(1)
        try:
            if self.owner_check:
                await self.owner_check()
            yield
        finally:
            self._depth.reset(token)
            self.active -= 1
            if not self.active:
                self._empty.set()

    @asynccontextmanager
    async def exclusive(self, kind: str):
        if self._depth.get():
            raise RuntimeError("Maintenance cannot drain its own admitted operation")
        self.assert_ready()
        self.state, self.kind = "draining", kind
        token = maintenance_context.set(True)
        try:
            if self.owner_check:
                await self.owner_check()
            try:
                await asyncio.wait_for(self._empty.wait(), timeout=self.drain_timeout)
            except TimeoutError as exc:
                raise HTTPException(409, "Active work did not finish; maintenance was not started") from exc
            self.state = "maintenance"
            if self.database_barrier:
                async with self.database_barrier():
                    yield
            else:
                yield
        finally:
            maintenance_context.reset(token)
            if self.state in {"draining", "maintenance"}:
                self.state, self.kind = "ready", None

    def block(self, state: str = "recovery-required"):
        self.state = state

    async def finish_recovery(self):
        if self.owner_check:
            await self.owner_check()
        if self.runtime_resume:
            try:
                await self.runtime_resume()
            except Exception:
                self.block('recovery-required')
                raise
        self.resume()

    def resume(self):
        if self.active:
            raise RuntimeError("Cannot resume while an operation remains active")
        self.state, self.kind = "ready", None

    def status(self):
        return {"state": self.state, "active_operations": self.active, "operation": self.kind}


coordinator = StationCoordinator()


class StationAdmissionMiddleware:
    """Drain full ordinary responses; previews acquire admission per frame instead."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        recovery_login = (path == "/api/v1/auth/login" and
                          coordinator.state in {"power-accepted", "recovery-required"})
        control = (recovery_login or path == "/health" or path.startswith("/api/v1/config/maintenance")
                   or path.startswith("/api/v1/config/operations/")
                   or path.startswith("/api/v1/config/backups")
                   or path.startswith("/api/v1/config/restores")
                   or path.startswith("/api/v1/config/power/")
                   or path in {"/api/v1/config/restart", "/api/v1/config/shutdown"}
                   or path.startswith("/api/v1/cameras/preview/"))
        if scope["type"] != "http" or control:
            token = maintenance_context.set(control)
            try:
                await self.app(scope, receive, send)
            finally:
                maintenance_context.reset(token)
            return
        try:
            async with coordinator.operation():
                await self.app(scope, receive, send)
        except HTTPException as exc:
            from starlette.responses import JSONResponse
            await JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                               headers=exc.headers)(scope, receive, send)
