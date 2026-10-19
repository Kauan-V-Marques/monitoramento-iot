"""Recebe as mensagens MQTT, grava no banco, avalia alertas e avisa o painel ao vivo."""

import asyncio
import json
import logging

import aiomqtt
from pydantic import ValidationError

from plataforma.alertas import AvaliadorAlertas, TipoAlerta
from plataforma.banco import Repositorio
from plataforma.modelos import Leitura
from plataforma.tempo_real import Hub

log = logging.getLogger("plataforma.ingestao")

TOPICO_TELEMETRIA = "fabrica/+/telemetria"
TOPICO_STATUS = "fabrica/+/status"


class Ingestor:
    def __init__(self, repo: Repositorio, hub: Hub, avaliador: AvaliadorAlertas | None = None):
        self.repo = repo
        self.hub = hub
        self.avaliador = avaliador or AvaliadorAlertas()
        self.recebidas = 0
        self.rejeitadas = 0

    async def restaurar_alertas(self) -> None:
        """Ao reiniciar, retoma os alertas que estavam abertos no banco."""
        for maquina, tipo in await self.repo.alertas_abertos():
            self.avaliador.restaurar(maquina, tipo)

    async def processar(self, topico: str, payload: bytes) -> None:
        partes = topico.split("/")
        if len(partes) != 3 or partes[0] != "fabrica":
            return
        maquina_topico, tipo_mensagem = partes[1], partes[2]

        if tipo_mensagem == "status":
            online = payload.decode(errors="ignore").strip() == "online"
            await self.repo.definir_online(maquina_topico, online)
            await self.hub.enviar({"tipo": "status", "maquina": maquina_topico, "online": online})
            return

        try:
            leitura = Leitura.model_validate_json(payload)
        except ValidationError as erro:
            self.rejeitadas += 1
            log.warning("mensagem inválida em %s: %s", topico, erro.errors(include_url=False))
            return
        if leitura.maquina != maquina_topico:
            self.rejeitadas += 1
            log.warning("máquina do JSON (%s) difere do tópico (%s)", leitura.maquina, maquina_topico)
            return

        self.recebidas += 1
        maquina = await self.repo.registrar(leitura)
        await self.hub.enviar(
            {"tipo": "leitura", **json.loads(leitura.model_dump_json()), "ts": leitura.instante().isoformat()}
        )

        for tipo, valor, limite in (
            (TipoAlerta.TEMPERATURA, leitura.temperatura_c, maquina["limite_temperatura_c"]),
            (TipoAlerta.VIBRACAO, leitura.vibracao_rms_g, maquina["limite_vibracao_g"]),
        ):
            evento = self.avaliador.avaliar(leitura.maquina, tipo, valor, limite)
            if evento:
                await self.repo.registrar_evento(evento, leitura.instante())
                log.info(
                    "alerta %s: %s em %s (%.2f / limite %.2f)",
                    "aberto" if evento.abriu else "encerrado",
                    tipo,
                    leitura.maquina,
                    valor,
                    limite,
                )
                await self.hub.enviar(
                    {
                        "tipo": "alerta",
                        "maquina": evento.maquina,
                        "alerta": tipo.value,
                        "aberto": evento.abriu,
                        "valor": evento.valor,
                        "limite": evento.limite,
                    }
                )

    async def rodar(self, host: str, porta: int) -> None:
        """Fica conectado ao broker para sempre, reconectando com espera crescente se cair."""
        espera = 1
        while True:
            try:
                async with aiomqtt.Client(host, porta, identifier="plataforma-ingestor") as cliente:
                    await cliente.subscribe(TOPICO_TELEMETRIA, qos=1)
                    await cliente.subscribe(TOPICO_STATUS, qos=1)
                    log.info("conectado ao broker %s:%s", host, porta)
                    espera = 1
                    async for mensagem in cliente.messages:
                        await self.processar(str(mensagem.topic), bytes(mensagem.payload))
            except aiomqtt.MqttError as erro:
                log.warning("broker indisponível (%s); nova tentativa em %ss", erro, espera)
                await asyncio.sleep(espera)
                espera = min(espera * 2, 30)
