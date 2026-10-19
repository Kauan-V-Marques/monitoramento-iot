"""Ponta a ponta com broker MQTT de verdade: simulador -> broker -> plataforma -> banco.

Só roda com MQTT_TEST_HOST definido (no CI há um Mosquitto).
"""

import os
import time

import pytest
from fastapi.testclient import TestClient

from plataforma.app import criar_app
from plataforma.simulador import simular

BROKER = os.environ.get("MQTT_TEST_HOST")
pytestmark = [pytest.mark.mqtt, pytest.mark.skipif(not BROKER, reason="defina MQTT_TEST_HOST")]


def esperar(condicao, segundos=15.0):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicao():
            return True
        time.sleep(0.2)
    return False


def test_leituras_do_simulador_chegam_pelo_broker(database_url):
    app = criar_app(database_url=database_url, mqtt_host=BROKER, mqtt_porta=1883, mqtt_ativo=True)
    with TestClient(app) as cliente:
        # Dá tempo de o ingestor conectar e assinar os tópicos antes de publicar
        assert esperar(lambda: True, 1.5)
        cliente.portal.call(simular, BROKER, 1883, 3, 0.05, 10)

        assert esperar(lambda: cliente.get("/api/saude").json()["mensagens_recebidas"] >= 30)
        maquinas = {m["id"]: m for m in cliente.get("/api/maquinas").json()}
        assert {"torno-01", "fresa-02", "prensa-03"} <= set(maquinas)
        assert all(m["online"] for m in maquinas.values())
