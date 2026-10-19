import json

import pytest

from plataforma.simulador import criar_maquinas


def leitura(maquina="torno-01", temp=50.0, vib=0.3, corrente=6.0, rpm=1450):
    return json.dumps(
        {"maquina": maquina, "temperatura_c": temp, "vibracao_rms_g": vib, "corrente_a": corrente, "rpm": rpm}
    ).encode()


def enviar(cliente, payload, maquina="torno-01", tipo="telemetria"):
    """Entrega a mensagem como se tivesse chegado do broker MQTT."""
    cliente.portal.call(cliente.app.state.ingestor.processar, f"fabrica/{maquina}/{tipo}", payload)


def test_primeira_leitura_cadastra_a_maquina_com_limites_padrao(cliente):
    enviar(cliente, leitura(temp=51.5))

    maquinas = cliente.get("/api/maquinas").json()

    assert len(maquinas) == 1
    assert maquinas[0]["id"] == "torno-01"
    assert maquinas[0]["online"] is True
    assert maquinas[0]["temperatura_c"] == pytest.approx(51.5)
    assert maquinas[0]["limite_temperatura_c"] == 80


def test_mensagens_invalidas_sao_rejeitadas_sem_derrubar_nada(cliente):
    enviar(cliente, b"isto nao e json")
    enviar(cliente, leitura(vib=-1))  # vibração negativa
    enviar(cliente, leitura(maquina="outra-maquina"), maquina="torno-01")  # JSON e tópico não batem

    saude = cliente.get("/api/saude").json()

    assert saude["mensagens_rejeitadas"] == 3
    assert cliente.get("/api/maquinas").json() == []


def test_superaquecimento_abre_alerta_e_resfriamento_fecha(cliente):
    for temp in (85, 86, 87):
        enviar(cliente, leitura(temp=temp))
    abertos = cliente.get("/api/alertas?abertos=true").json()
    assert [(a["tipo"], a["valor"]) for a in abertos] == [("temperatura", 87)]
    assert cliente.get("/api/maquinas").json()[0]["alertas_abertos"] == 1

    for temp in (60, 60, 60):
        enviar(cliente, leitura(temp=temp))

    assert cliente.get("/api/alertas?abertos=true").json() == []
    historico = cliente.get("/api/alertas").json()
    assert historico[0]["fim"] is not None


def test_limites_por_maquina(cliente):
    enviar(cliente, leitura())

    resposta = cliente.put(
        "/api/maquinas/torno-01/limites", json={"limite_temperatura_c": 60, "limite_vibracao_g": 0.5}
    )
    for _ in range(3):
        enviar(cliente, leitura(temp=65))

    assert resposta.status_code == 200
    assert cliente.get("/api/alertas?abertos=true").json()[0]["limite"] == 60
    assert (
        cliente.put(
            "/api/maquinas/nao-existe/limites", json={"limite_temperatura_c": 60, "limite_vibracao_g": 0.5}
        ).status_code
        == 404
    )


def test_historico_agrupa_por_intervalo(cliente):
    for temp in (40, 50, 60):
        enviar(cliente, leitura(temp=temp, vib=0.2 + temp / 1000))

    pontos = cliente.get("/api/maquinas/torno-01/historico?minutos=5&pontos=10").json()

    assert 1 <= len(pontos) <= 2
    assert sum(p["temperatura_c"] for p in pontos) / len(pontos) == pytest.approx(50, abs=10)
    assert cliente.get("/api/maquinas/nao-existe/historico").status_code == 404


def test_status_online_offline_pelo_last_will(cliente):
    enviar(cliente, leitura())
    enviar(cliente, b"offline", tipo="status")

    assert cliente.get("/api/maquinas").json()[0]["online"] is False


def test_painel_recebe_leituras_e_alertas_ao_vivo(cliente):
    with cliente.websocket_connect("/ws") as ws:
        for temp in (90, 91, 92):
            enviar(cliente, leitura(temp=temp))
        eventos = [ws.receive_json() for _ in range(4)]

    assert [e["tipo"] for e in eventos] == ["leitura", "leitura", "leitura", "alerta"]
    assert eventos[-1]["aberto"] is True
    assert eventos[-1]["maquina"] == "torno-01"


def test_dados_do_simulador_passam_na_validacao(cliente):
    maquinas = criar_maquinas(5)
    for _ in range(20):
        for m in maquinas:
            enviar(cliente, json.dumps(m.leitura()).encode(), maquina=m.nome)

    saude = cliente.get("/api/saude").json()
    assert saude["mensagens_recebidas"] == 100
    assert saude["mensagens_rejeitadas"] == 0
    assert len(cliente.get("/api/maquinas").json()) == 5


def test_painel_web_e_servido(cliente):
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "Monitoramento de Máquinas" in resposta.text
    assert cliente.get("/painel/painel.js").status_code == 200


def test_leituras_vira_hypertable_quando_ha_timescaledb(cliente, database_url):
    import psycopg

    with psycopg.connect(database_url) as conn:
        tem_timescale = conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'").fetchone()
        if not tem_timescale:
            pytest.skip("TimescaleDB não instalado neste PostgreSQL")
        hypertables = conn.execute(
            "SELECT hypertable_name FROM timescaledb_information.hypertables"
        ).fetchall()

    assert ("leituras",) in hypertables
