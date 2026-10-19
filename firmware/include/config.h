#pragma once

// Identificação da máquina (vira parte dos tópicos MQTT)
#define ID_MAQUINA "torno-01"

// Pinos (ESP32 DevKit)
#define PINO_TERMISTOR 34   // ADC1
#define PINO_CORRENTE 35    // ADC1
#define PINO_ROTACAO 27     // sensor indutivo, 1 pulso por volta
#define PINO_SDA 21
#define PINO_SCL 22
#define ENDERECO_MPU 0x68

#define PULSOS_POR_VOLTA 1
#define AMOSTRAS_VIBRACAO 200
#define INTERVALO_PADRAO_MS 2000
