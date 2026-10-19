from plataforma.alertas import AvaliadorAlertas, TipoAlerta

T = TipoAlerta.TEMPERATURA


def avaliar_sequencia(valores, limite=80.0, avaliador=None):
    avaliador = avaliador or AvaliadorAlertas(leituras_para_mudar=3)
    return [avaliador.avaliar("torno-01", T, v, limite) for v in valores]


def test_uma_leitura_isolada_acima_do_limite_nao_abre_alerta():
    eventos = avaliar_sequencia([70, 95, 70, 70, 96, 71])

    assert all(e is None for e in eventos)


def test_tres_leituras_seguidas_abrem_o_alerta_uma_unica_vez():
    eventos = avaliar_sequencia([85, 86, 87, 88, 89])

    abertos = [e for e in eventos if e]
    assert len(abertos) == 1
    assert eventos[2].abriu and eventos[2].valor == 87


def test_alerta_so_fecha_depois_de_tres_leituras_normais():
    avaliador = AvaliadorAlertas(leituras_para_mudar=3)
    avaliar_sequencia([90, 90, 90], avaliador=avaliador)

    eventos = avaliar_sequencia([70, 85, 70, 70, 70], avaliador=avaliador)

    # A leitura de 85 no meio zera a contagem: o alerta só fecha na última
    assert eventos[:4] == [None, None, None, None]
    assert eventos[4] is not None and not eventos[4].abriu


def test_valor_igual_ao_limite_nao_dispara():
    assert all(e is None for e in avaliar_sequencia([80, 80, 80, 80]))


def test_sensor_com_defeito_nao_muda_o_estado():
    avaliador = AvaliadorAlertas(leituras_para_mudar=2)
    avaliar_sequencia([90], avaliador=avaliador)

    eventos = avaliar_sequencia([None, 90], avaliador=avaliador)

    assert eventos[1] is not None and eventos[1].abriu


def test_maquinas_e_tipos_sao_independentes():
    avaliador = AvaliadorAlertas(leituras_para_mudar=2)
    for _ in range(2):
        avaliador.avaliar("torno-01", T, 90, 80)
        avaliador.avaliar("fresa-02", T, 50, 80)
        avaliador.avaliar("torno-01", TipoAlerta.VIBRACAO, 0.2, 0.8)

    assert avaliador.ativos() == {("torno-01", T)}


def test_restaurar_alerta_aberto_depois_de_reiniciar():
    avaliador = AvaliadorAlertas(leituras_para_mudar=2)
    avaliador.restaurar("torno-01", T)

    eventos = avaliar_sequencia([70, 70], avaliador=avaliador)

    assert eventos[1] is not None and not eventos[1].abriu
