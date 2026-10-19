#include <string.h>
#include <unity.h>

#include "Sensores.h"

using namespace sensores;

void setUp() {}
void tearDown() {}

void test_termistor_a_25_graus() {
    // Com NTC = resistor fixo (10k a 25 °C) o divisor fica no meio da escala
    TEST_ASSERT_FLOAT_WITHIN(0.2f, 25.0f, temperaturaC(2048));
}

void test_termistor_esquenta_quando_a_resistencia_cai() {
    // NTC: mais quente = menor resistência = menor tensão no ADC
    const float quente = temperaturaC(1000);
    const float frio = temperaturaC(3000);
    TEST_ASSERT_TRUE(quente > 25.0f);
    TEST_ASSERT_TRUE(frio < 25.0f);
}

void test_termistor_valor_conhecido() {
    // R = 3,6 kΩ: 1/T = 1/298,15 + ln(0,36)/3950  ->  T = 323,06 K = 49,9 °C
    const uint16_t adc = static_cast<uint16_t>(4095.0f * 3600.0f / (10000.0f + 3600.0f));
    TEST_ASSERT_FLOAT_WITHIN(0.3f, 49.9f, temperaturaC(adc));
}

void test_termistor_desconectado_ou_em_curto_vira_nan() {
    TEST_ASSERT_TRUE(isnan(temperaturaC(0)));
    TEST_ASSERT_TRUE(isnan(temperaturaC(4095)));
}

void test_vibracao_rms_ignora_a_gravidade() {
    const float parado[] = {1.0f, 1.0f, 1.0f, 1.0f};
    TEST_ASSERT_FLOAT_WITHIN(1e-6f, 0.0f, vibracaoRms(parado, 4));

    // Oscilação de ±0,5 g em torno de 1 g: RMS = 0,5
    const float vibrando[] = {1.5f, 0.5f, 1.5f, 0.5f};
    TEST_ASSERT_FLOAT_WITHIN(1e-5f, 0.5f, vibracaoRms(vibrando, 4));
    TEST_ASSERT_EQUAL_FLOAT(0.0f, vibracaoRms(vibrando, 0));
}

void test_modulo_da_aceleracao_do_mpu6050() {
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 1.0f, moduloAceleracaoG(0, 0, 16384));
    TEST_ASSERT_FLOAT_WITHIN(1e-4f, 1.0f, moduloAceleracaoG(9830, 0, 13107));  // 0,6 g e 0,8 g
}

void test_corrente_zero_e_10_amperes() {
    // 2,5 V no sensor -> 1,65 V no ADC -> metade da escala
    TEST_ASSERT_FLOAT_WITHIN(0.05f, 0.0f, correnteA(2048));
    // 10 A -> 3,5 V no sensor -> 2,31 V no ADC
    const uint16_t adc10 = static_cast<uint16_t>(4095.0f * (3.5f * 0.66f) / 3.3f);
    TEST_ASSERT_FLOAT_WITHIN(0.1f, 10.0f, correnteA(adc10));
}

void test_json_da_telemetria() {
    char buffer[200];
    Leitura l = {54.256f, 0.3123f, 6.8f, 1450.0f};

    const int n = montarJson(buffer, sizeof buffer, "torno-01", l);

    TEST_ASSERT_EQUAL_STRING(
        "{\"maquina\":\"torno-01\",\"temperatura_c\":54.26,\"vibracao_rms_g\":0.312,"
        "\"corrente_a\":6.80,\"rpm\":1450}",
        buffer);
    TEST_ASSERT_EQUAL_INT(static_cast<int>(strlen(buffer)), n);
}

void test_json_com_sensor_com_defeito_e_buffer_pequeno() {
    char buffer[200];
    Leitura l = {NAN, 0.1f, 1.0f, 0.0f};
    montarJson(buffer, sizeof buffer, "prensa-02", l);
    TEST_ASSERT_NOT_NULL(strstr(buffer, "\"temperatura_c\":null"));

    char pequeno[20];
    TEST_ASSERT_EQUAL_INT(-1, montarJson(pequeno, sizeof pequeno, "prensa-02", l));
}

int main(int, char**) {
    UNITY_BEGIN();
    RUN_TEST(test_termistor_a_25_graus);
    RUN_TEST(test_termistor_esquenta_quando_a_resistencia_cai);
    RUN_TEST(test_termistor_valor_conhecido);
    RUN_TEST(test_termistor_desconectado_ou_em_curto_vira_nan);
    RUN_TEST(test_vibracao_rms_ignora_a_gravidade);
    RUN_TEST(test_modulo_da_aceleracao_do_mpu6050);
    RUN_TEST(test_corrente_zero_e_10_amperes);
    RUN_TEST(test_json_da_telemetria);
    RUN_TEST(test_json_com_sensor_com_defeito_e_buffer_pequeno);
    return UNITY_END();
}
