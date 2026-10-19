#pragma once
// Conversões dos sensores em funções puras: não dependem do Arduino e são testadas no PC.

#include <math.h>
#include <stdint.h>
#include <stdio.h>

namespace sensores {

// ---------------------------------------------------------------- temperatura
// Termistor NTC 10k (B = 3950) num divisor de tensão com resistor fixo de 10k:
//   3V3 -- [10k fixo] --+-- [NTC] -- GND      (ADC lê o ponto do meio)
struct Termistor {
    float rFixo = 10000.0f;     // ohms
    float rNominal = 10000.0f;  // resistência do NTC a 25 °C
    float beta = 3950.0f;
    float tNominalK = 298.15f;  // 25 °C em kelvin
    uint16_t adcMax = 4095;     // ESP32: 12 bits
};

// Resistência do NTC a partir da leitura do ADC
inline float resistenciaNtc(uint16_t adc, const Termistor& t = Termistor()) {
    if (adc == 0) return 0.0f;
    if (adc >= t.adcMax) return INFINITY;
    return t.rFixo * adc / static_cast<float>(t.adcMax - adc);
}

// Equação do parâmetro Beta: 1/T = 1/T0 + ln(R/R0)/B
inline float temperaturaC(uint16_t adc, const Termistor& t = Termistor()) {
    const float r = resistenciaNtc(adc, t);
    if (r <= 0.0f || isinf(r)) return NAN;  // sensor em curto ou desconectado
    const float inversoT = 1.0f / t.tNominalK + logf(r / t.rNominal) / t.beta;
    return 1.0f / inversoT - 273.15f;
}

// ---------------------------------------------------------------- vibração
// RMS da aceleração (em g) já sem a componente constante (gravidade/inclinação).
// Recebe as amostras do módulo da aceleração de uma janela curta.
inline float vibracaoRms(const float* amostras, uint16_t n) {
    if (n == 0) return 0.0f;
    float media = 0.0f;
    for (uint16_t i = 0; i < n; i++) media += amostras[i];
    media /= n;

    float soma = 0.0f;
    for (uint16_t i = 0; i < n; i++) {
        const float d = amostras[i] - media;
        soma += d * d;
    }
    return sqrtf(soma / n);
}

// Módulo do vetor de aceleração a partir dos valores brutos do MPU-6050 (escala ±2 g)
inline float moduloAceleracaoG(int16_t ax, int16_t ay, int16_t az) {
    const float lsbPorG = 16384.0f;
    const float x = ax / lsbPorG, y = ay / lsbPorG, z = az / lsbPorG;
    return sqrtf(x * x + y * y + z * z);
}

// ---------------------------------------------------------------- corrente
// Sensor de efeito Hall ACS712-20A: 2,5 V em 0 A e 100 mV/A (com divisor para o ADC de 3,3 V)
struct SensorCorrente {
    float vZero = 2.5f;           // tensão de saída em 0 A
    float sensibilidade = 0.100f;  // V/A
    float divisor = 3.3f / 5.0f;   // divisor resistivo 5 V -> 3,3 V
    float vRef = 3.3f;
    uint16_t adcMax = 4095;
};

inline float correnteA(uint16_t adc, const SensorCorrente& s = SensorCorrente()) {
    const float vAdc = adc * s.vRef / s.adcMax;
    const float vSensor = vAdc / s.divisor;
    return fabsf((vSensor - s.vZero) / s.sensibilidade);
}

// ---------------------------------------------------------------- telemetria
struct Leitura {
    float temperaturaC;
    float vibracaoRmsG;
    float correnteA;
    float rpm;
};

// JSON publicado no tópico fabrica/<maquina>/telemetria. Retorna o tamanho escrito
// ou -1 se não couber. Valores inválidos (NaN) viram null.
inline int montarJson(char* destino, size_t tamanho, const char* maquina, const Leitura& l) {
    char temp[16];
    if (isnan(l.temperaturaC)) snprintf(temp, sizeof temp, "null");
    else snprintf(temp, sizeof temp, "%.2f", l.temperaturaC);

    const int n = snprintf(destino, tamanho,
                           "{\"maquina\":\"%s\",\"temperatura_c\":%s,\"vibracao_rms_g\":%.3f,"
                           "\"corrente_a\":%.2f,\"rpm\":%.0f}",
                           maquina, temp, l.vibracaoRmsG, l.correnteA, l.rpm);
    return (n < 0 || static_cast<size_t>(n) >= tamanho) ? -1 : n;
}

}  // namespace sensores
