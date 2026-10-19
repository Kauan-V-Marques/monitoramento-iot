"""API REST + WebSocket + painel web."""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from importlib import resources

import aiomqtt
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from plataforma.banco import Repositorio
from plataforma.ingestao import Ingestor
from plataforma.modelos import ID_MAQUINA, Comando, Limites
from plataforma.tempo_real import Hub

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def criar_app(
    database_url: str | None = None,
    mqtt_host: str | None = None,
    mqtt_porta: int | None = None,
    mqtt_ativo: bool | None = None,
) -> FastAPI:
    database_url = database_url or os.environ.get("DATABASE_URL", "postgresql://iot:iot@localhost:5432/iot")
    mqtt_host = mqtt_host or os.environ.get("MQTT_HOST", "localhost")
    mqtt_porta = mqtt_porta or int(os.environ.get("MQTT_PORT", "1883"))
    if mqtt_ativo is None:
        mqtt_ativo = os.environ.get("MQTT_ATIVO", "true") == "true"

    repo = Repositorio(database_url)
    hub = Hub()
    ingestor = Ingestor(repo, hub)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        await repo.abrir()
        await ingestor.restaurar_alertas()
        tarefa = asyncio.create_task(ingestor.rodar(mqtt_host, mqtt_porta)) if mqtt_ativo else None
        yield
        if tarefa:
            tarefa.cancel()
        await repo.fechar()

    app = FastAPI(title="Monitoramento de Máquinas", version="1.0.0", lifespan=ciclo_de_vida)
    app.state.repo, app.state.hub, app.state.ingestor = repo, hub, ingestor

    @app.get("/api/saude")
    async def saude():
        return {
            "status": "ok",
            "mensagens_recebidas": ingestor.recebidas,
            "mensagens_rejeitadas": ingestor.rejeitadas,
            "paineis_conectados": hub.conectados,
        }

    @app.get("/api/maquinas")
    async def maquinas():
        return await repo.maquinas()

    @app.get("/api/maquinas/{maquina_id}/historico")
    async def historico(
        maquina_id: str,
        minutos: int = Query(30, ge=1, le=24 * 60),
        pontos: int = Query(60, ge=10, le=500),
    ):
        if not await repo.maquina(maquina_id):
            raise HTTPException(404, "Máquina não encontrada.")
        passo = max(1, minutos * 60 // pontos)
        return await repo.historico(maquina_id, minutos, passo)

    @app.put("/api/maquinas/{maquina_id}/limites")
    async def definir_limites(maquina_id: str, limites: Limites):
        maquina = await repo.definir_limites(
            maquina_id, limites.limite_temperatura_c, limites.limite_vibracao_g
        )
        if not maquina:
            raise HTTPException(404, "Máquina não encontrada.")
        return maquina

    @app.post("/api/maquinas/{maquina_id}/comando", status_code=202)
    async def enviar_comando(maquina_id: str, comando: Comando):
        if not re.match(ID_MAQUINA, maquina_id) or not await repo.maquina(maquina_id):
            raise HTTPException(404, "Máquina não encontrada.")
        try:
            async with aiomqtt.Client(mqtt_host, mqtt_porta) as cliente:
                await cliente.publish(
                    f"fabrica/{maquina_id}/comando", json.dumps(comando.model_dump()), qos=1
                )
        except aiomqtt.MqttError as erro:
            raise HTTPException(503, "Broker MQTT indisponível.") from erro
        return {"enviado": True}

    @app.get("/api/alertas")
    async def alertas(abertos: bool = False):
        return await repo.alertas(apenas_abertos=abertos)

    @app.websocket("/ws")
    async def tempo_real(ws: WebSocket):
        await hub.conectar(ws)
        try:
            while True:
                await ws.receive_text()  # mantém a conexão; o painel não envia nada
        except WebSocketDisconnect:
            hub.desconectar(ws)

    estaticos = resources.files("plataforma").joinpath("painel")
    app.mount("/painel", StaticFiles(directory=str(estaticos)), name="painel")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def inicio():
        return estaticos.joinpath("index.html").read_text(encoding="utf-8")

    return app
