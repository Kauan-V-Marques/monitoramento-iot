"""Cada sessão de testes cria um banco próprio e o apaga no final.

Servidor: TEST_DATABASE_URL (padrão postgresql://iot:iot@localhost:5432/iot).
"""

import asyncio
import os
import sys
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from plataforma.app import criar_app

# O psycopg assíncrono não funciona com o loop padrão do Windows (Proactor)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

SERVIDOR = os.environ.get("TEST_DATABASE_URL", "postgresql://iot:iot@localhost:5432/iot")


@pytest.fixture(scope="session")
def database_url():
    nome = f"iot_teste_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(SERVIDOR, autocommit=True) as conn:
        conn.execute(f"CREATE DATABASE {nome}")
    base, _, _ = SERVIDOR.rpartition("/")
    yield f"{base}/{nome}"
    with psycopg.connect(SERVIDOR, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {nome} WITH (FORCE)")


@pytest.fixture()
def cliente(database_url):
    """App completo sem conectar ao broker: as mensagens entram por app.state.ingestor.processar."""
    app = criar_app(database_url=database_url, mqtt_ativo=False)
    with TestClient(app) as cliente:
        with psycopg.connect(database_url, autocommit=True) as conn:
            conn.execute("TRUNCATE alertas, leituras, maquinas RESTART IDENTITY CASCADE")
        app.state.ingestor.avaliador._estados.clear()
        yield cliente
