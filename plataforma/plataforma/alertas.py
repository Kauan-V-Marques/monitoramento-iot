"""Regras de alerta com histerese.

Um alerta abre depois de N leituras seguidas acima do limite e fecha depois de N
leituras seguidas abaixo. Assim uma leitura isolada com ruído não liga nem desliga
o alarme, e ele não fica "piscando" quando o valor oscila perto do limite.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class TipoAlerta(StrEnum):
    TEMPERATURA = "temperatura"
    VIBRACAO = "vibracao"


@dataclass(frozen=True)
class Evento:
    maquina: str
    tipo: TipoAlerta
    abriu: bool  # True = alerta começou; False = alerta terminou
    valor: float
    limite: float


@dataclass
class _Estado:
    ativo: bool = False
    seguidas: int = 0  # leituras seguidas no sentido contrário ao estado atual


@dataclass
class AvaliadorAlertas:
    leituras_para_mudar: int = 3
    _estados: dict[tuple[str, TipoAlerta], _Estado] = field(default_factory=dict)

    def avaliar(self, maquina: str, tipo: TipoAlerta, valor: float | None, limite: float) -> Evento | None:
        if valor is None:  # sensor com defeito: não decide nada com base nele
            return None

        estado = self._estados.setdefault((maquina, tipo), _Estado())
        fora_do_limite = valor > limite

        if fora_do_limite != estado.ativo:
            estado.seguidas += 1
        else:
            estado.seguidas = 0

        if estado.seguidas >= self.leituras_para_mudar:
            estado.ativo = not estado.ativo
            estado.seguidas = 0
            return Evento(maquina, tipo, estado.ativo, valor, limite)
        return None

    def restaurar(self, maquina: str, tipo: TipoAlerta) -> None:
        """Marca um alerta como ativo (ex.: alerta aberto no banco ao reiniciar o serviço)."""
        self._estados[(maquina, tipo)] = _Estado(ativo=True)

    def ativos(self) -> set[tuple[str, TipoAlerta]]:
        return {chave for chave, estado in self._estados.items() if estado.ativo}
