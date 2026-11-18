"""Limite de tamanho do corpo das requisições.

O Starlette grava o upload multipart em disco antes de a rota rodar. Sem este limite,
um envio de gigabytes ocuparia o disco antes de a rota recusar o arquivo.
Em produção, o proxy reverso também deve limitar (defesa em profundidade).
"""

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _TooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_bytes: int,
        overrides: tuple[tuple[str, int], ...] = (),
    ):
        """`overrides`: (regex do caminho, limite) para rotas que aceitam arquivos maiores
        (ex.: envio de raio-X). Valem só para POST."""
        self.app = app
        self.max_bytes = max_bytes
        self.overrides = tuple((re.compile(p), n) for p, n in overrides)

    def _limit(self, scope: Scope) -> int:
        if scope.get("method") == "POST":
            for pattern, limit in self.overrides:
                if pattern.fullmatch(scope.get("path", "")):
                    return limit
        return self.max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self._limit(scope)
        declared = dict(scope.get("headers") or []).get(b"content-length")
        if declared is not None:
            try:
                too_big = int(declared) > max_bytes
            except ValueError:
                too_big = True
            if too_big:
                await self._reject(send)
                return

        # Sem Content-Length (envio em partes), conta os bytes conforme chegam.
        received = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    raise _TooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except _TooLarge:
            if not response_started:
                await self._reject(send)

    async def _reject(self, send: Send) -> None:
        body = '{"detail":"Requisição grande demais."}'.encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
