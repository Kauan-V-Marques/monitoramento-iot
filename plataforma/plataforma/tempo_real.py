"""Distribui os eventos para todos os navegadores conectados por WebSocket."""

import asyncio
import json

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self._clientes: set[WebSocket] = set()

    async def conectar(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clientes.add(ws)

    def desconectar(self, ws: WebSocket) -> None:
        self._clientes.discard(ws)

    @property
    def conectados(self) -> int:
        return len(self._clientes)

    async def enviar(self, evento: dict) -> None:
        if not self._clientes:
            return
        texto = json.dumps(evento, default=str)
        resultados = await asyncio.gather(
            *(ws.send_text(texto) for ws in self._clientes), return_exceptions=True
        )
        # Quem fechou a aba sai da lista
        for ws, resultado in zip(list(self._clientes), resultados, strict=False):
            if isinstance(resultado, Exception):
                self.desconectar(ws)
