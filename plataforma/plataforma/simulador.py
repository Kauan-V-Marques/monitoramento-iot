"""Simula máquinas publicando telemetria via MQTT (para testar sem hardware).

python -m plataforma.simulador --broker localhost --maquinas 4

Cada máquina tem um comportamento: normal, superaquecendo aos poucos ou com o
rolamento se desgastando (vibração crescente), para os alertas aparecerem.
"""

import argparse
import asyncio
import json
import math
import random
from dataclasses import dataclass

import aiomqtt

PERFIS = ["normal", "superaquecimento", "rolamento", "normal", "intermitente"]
NOMES = [
    "torno-01",
    "fresa-02",
    "prensa-03",
    "compressor-04",
    "esteira-05",
    "torno-06",
    "fresa-07",
    "prensa-08",
]


@dataclass
class MaquinaSimulada:
    nome: str
    perfil: str
    semente: int
    passo: int = 0

    def __post_init__(self):
        self.rng = random.Random(self.semente)
        self.rpm_nominal = self.rng.choice([900, 1200, 1450, 1750])

    def leitura(self) -> dict:
        """Próxima leitura: valores base + ruído + o defeito do perfil."""
        self.passo += 1
        t = self.passo
        temperatura = 45 + 6 * math.sin(t / 40) + self.rng.gauss(0, 0.8)
        vibracao = 0.25 + self.rng.gauss(0, 0.03)
        corrente = 6 + 0.8 * math.sin(t / 25) + self.rng.gauss(0, 0.2)

        if self.perfil == "superaquecimento":
            temperatura += min(45, t * 0.25)  # sobe devagar até passar do limite
        elif self.perfil == "rolamento":
            vibracao += min(1.2, (t / 120) ** 2)  # desgaste acelera
        elif self.perfil == "intermitente" and (t // 30) % 4 == 3:
            vibracao += 0.9  # picos periódicos

        return {
            "maquina": self.nome,
            "temperatura_c": round(temperatura, 2),
            "vibracao_rms_g": round(max(0.0, vibracao), 3),
            "corrente_a": round(max(0.0, corrente), 2),
            "rpm": round(self.rpm_nominal + self.rng.gauss(0, 8)),
        }


def criar_maquinas(quantidade: int, semente: int = 7) -> list[MaquinaSimulada]:
    return [
        MaquinaSimulada(NOMES[i % len(NOMES)], PERFIS[i % len(PERFIS)], semente + i)
        for i in range(quantidade)
    ]


async def simular(broker: str, porta: int, quantidade: int, intervalo: float, leituras: int | None) -> None:
    maquinas = criar_maquinas(quantidade)
    async with aiomqtt.Client(broker, porta, identifier="simulador") as cliente:
        for m in maquinas:
            await cliente.publish(f"fabrica/{m.nome}/status", "online", qos=1, retain=True)
        enviadas = 0
        while leituras is None or enviadas < leituras:
            for m in maquinas:
                await cliente.publish(f"fabrica/{m.nome}/telemetria", json.dumps(m.leitura()), qos=1)
            enviadas += 1
            await asyncio.sleep(intervalo)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--broker", default="localhost")
    parser.add_argument("--porta", type=int, default=1883)
    parser.add_argument("--maquinas", type=int, default=4)
    parser.add_argument("--intervalo", type=float, default=1.0, help="segundos entre leituras")
    parser.add_argument(
        "--leituras", type=int, default=None, help="para depois de N rodadas (padrão: infinito)"
    )
    args = parser.parse_args()
    asyncio.run(simular(args.broker, args.porta, args.maquinas, args.intervalo, args.leituras))


if __name__ == "__main__":
    main()
