"""Formato das mensagens que chegam das máquinas."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

ID_MAQUINA = r"^[a-z0-9][a-z0-9-]{1,39}$"


class Leitura(BaseModel):
    """JSON publicado em fabrica/<maquina>/telemetria."""

    model_config = ConfigDict(extra="ignore")

    maquina: str = Field(pattern=ID_MAQUINA)
    temperatura_c: float | None = Field(default=None, ge=-40, le=200)
    vibracao_rms_g: float = Field(ge=0, le=16)
    corrente_a: float = Field(ge=0, le=100)
    rpm: float = Field(default=0, ge=0, le=30_000)
    ts: datetime | None = None  # o ESP32 não tem relógio: sem ts, vale a hora de chegada

    def instante(self) -> datetime:
        return self.ts or datetime.now(UTC)


class Limites(BaseModel):
    limite_temperatura_c: float = Field(gt=0, le=200)
    limite_vibracao_g: float = Field(gt=0, le=16)


class Comando(BaseModel):
    intervalo_ms: int = Field(ge=500, le=60_000)
