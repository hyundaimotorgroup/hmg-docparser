"""ASGI request budgets, applied before JSON/multipart parsing and inference."""

from __future__ import annotations

import asyncio
import json


class RequestLimitsMiddleware:
    """Bound queued requests and receive bytes, with limits per application worker."""

    def __init__(
        self, app, *, paths: set[str], max_request_bytes: int,
        max_concurrent_requests: int, max_queued_requests: int,
        read_timeout_seconds: int = 900,
    ) -> None:
        self.app = app
        self.paths = paths
        self.max_bytes = max_request_bytes
        self.max_admitted = max_concurrent_requests + max_queued_requests
        self.slots = asyncio.Semaphore(max_concurrent_requests) if max_concurrent_requests else None
        self.admitted = 0
        self.read_timeout = read_timeout_seconds

    @staticmethod
    async def reject(send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
        if status == 503:
            headers.append((b"retry-after", b"1"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] not in self.paths:
            await self.app(scope, receive, send)
            return
        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        if lengths:
            try:
                if len(lengths) != 1:
                    raise ValueError
                length = int(lengths[0])
                if length < 0:
                    raise ValueError
            except ValueError:
                await self.reject(send, 400, "invalid Content-Length")
                return
            if self.max_bytes and length > self.max_bytes:
                await self.reject(send, 413, "request bytes exceed the configured limit")
                return
        # All increments precede awaits on the app's event loop. Waiting requests
        # have not yet buffered their image bodies or entered model/decode workers.
        if self.slots is not None and self.admitted >= self.max_admitted:
            await self.reject(send, 503, "request queue is full; retry later")
            return
        self.admitted += 1
        acquired = False
        try:
            if self.slots is not None:
                await self.slots.acquire()
                acquired = True
            body = bytearray()
            deadline = asyncio.get_running_loop().time() + self.read_timeout
            while True:
                try:
                    message = (
                        await asyncio.wait_for(receive(), max(0, deadline - asyncio.get_running_loop().time()))
                        if self.read_timeout else await receive()
                    )
                except TimeoutError:
                    await self.reject(send, 408, "request body read timed out")
                    return
                if message["type"] == "http.disconnect":
                    return
                chunk = message.get("body", b"")
                if self.max_bytes and len(body) + len(chunk) > self.max_bytes:
                    await self.reject(send, 413, "request bytes exceed the configured limit")
                    return
                body.extend(chunk)
                if not message.get("more_body", False):
                    break
            delivered = False
            payload = bytes(body)
            del body

            async def replay():
                nonlocal delivered, payload
                if not delivered:
                    delivered = True
                    message = {"type": "http.request", "body": payload, "more_body": False}
                    payload = b""
                    return message
                return await receive()

            await self.app(scope, replay, send)
        finally:
            if acquired:
                self.slots.release()
            self.admitted -= 1
