// Nó de monitoramento de máquina (ESP32)
// Lê temperatura (NTC), vibração (MPU-6050) e corrente (ACS712) e publica via MQTT:
//   fabrica/<maquina>/telemetria  -> JSON com as leituras
//   fabrica/<maquina>/status      -> "online" / "offline" (last will, retido)
//   fabrica/<maquina>/comando     <- {"intervalo_ms": 2000}

#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <Wire.h>

#include "Sensores.h"
#include "config.h"
#include "secrets.h"

WiFiClient rede;
PubSubClient mqtt(rede);

char topicoTelemetria[64], topicoStatus[64], topicoComando[64];
uint32_t intervaloMs = INTERVALO_PADRAO_MS;
uint32_t ultimaPublicacao = 0;
volatile uint32_t pulsos = 0;  // sensor indutivo de rotação

void IRAM_ATTR contarPulso() { pulsos++; }

// ---------------------------------------------------------------- MPU-6050 (I2C direto)

void iniciarMpu() {
    Wire.begin(PINO_SDA, PINO_SCL);
    Wire.beginTransmission(ENDERECO_MPU);
    Wire.write(0x6B);  // PWR_MGMT_1: tira do modo sleep
    Wire.write(0x00);
    Wire.endTransmission();
}

bool lerAceleracao(int16_t& ax, int16_t& ay, int16_t& az) {
    Wire.beginTransmission(ENDERECO_MPU);
    Wire.write(0x3B);  // ACCEL_XOUT_H
    if (Wire.endTransmission(false) != 0) return false;
    if (Wire.requestFrom((uint8_t)ENDERECO_MPU, (uint8_t)6) != 6) return false;
    ax = (Wire.read() << 8) | Wire.read();
    ay = (Wire.read() << 8) | Wire.read();
    az = (Wire.read() << 8) | Wire.read();
    return true;
}

float medirVibracao() {
    static float amostras[AMOSTRAS_VIBRACAO];
    uint16_t n = 0;
    for (uint16_t i = 0; i < AMOSTRAS_VIBRACAO; i++) {
        int16_t ax, ay, az;
        if (lerAceleracao(ax, ay, az)) amostras[n++] = sensores::moduloAceleracaoG(ax, ay, az);
        delayMicroseconds(1000);  // ~1 kHz de amostragem
    }
    return sensores::vibracaoRms(amostras, n);
}

// ---------------------------------------------------------------- MQTT

void aoReceberComando(char* topico, uint8_t* dados, unsigned int tamanho) {
    JsonDocument doc;
    if (deserializeJson(doc, dados, tamanho)) return;
    const uint32_t novo = doc["intervalo_ms"] | intervaloMs;
    intervaloMs = constrain(novo, 500u, 60000u);
    Serial.printf("Novo intervalo: %u ms\n", intervaloMs);
}

void garantirConexoes() {
    if (WiFi.status() != WL_CONNECTED) {
        WiFi.begin(WIFI_SSID, WIFI_SENHA);
        for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) delay(250);
    }
    if (WiFi.status() == WL_CONNECTED && !mqtt.connected()) {
        // Last will: se o ESP32 cair, o broker publica "offline" por ele
        if (mqtt.connect(ID_MAQUINA, MQTT_USUARIO, MQTT_SENHA, topicoStatus, 1, true, "offline")) {
            mqtt.publish(topicoStatus, "online", true);
            mqtt.subscribe(topicoComando);
        }
    }
}

// ---------------------------------------------------------------- setup / loop

void setup() {
    Serial.begin(115200);
    analogReadResolution(12);
    snprintf(topicoTelemetria, sizeof topicoTelemetria, "fabrica/%s/telemetria", ID_MAQUINA);
    snprintf(topicoStatus, sizeof topicoStatus, "fabrica/%s/status", ID_MAQUINA);
    snprintf(topicoComando, sizeof topicoComando, "fabrica/%s/comando", ID_MAQUINA);

    iniciarMpu();
    pinMode(PINO_ROTACAO, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PINO_ROTACAO), contarPulso, FALLING);

    WiFi.mode(WIFI_STA);
    mqtt.setServer(MQTT_HOST, MQTT_PORTA);
    mqtt.setCallback(aoReceberComando);
}

void loop() {
    garantirConexoes();
    mqtt.loop();

    const uint32_t agora = millis();
    if (agora - ultimaPublicacao < intervaloMs) return;
    const float segundos = (agora - ultimaPublicacao) / 1000.0f;
    ultimaPublicacao = agora;

    noInterrupts();
    const uint32_t voltas = pulsos;
    pulsos = 0;
    interrupts();

    sensores::Leitura leitura;
    leitura.temperaturaC = sensores::temperaturaC(analogRead(PINO_TERMISTOR));
    leitura.correnteA = sensores::correnteA(analogRead(PINO_CORRENTE));
    leitura.vibracaoRmsG = medirVibracao();
    leitura.rpm = voltas * 60.0f / segundos / PULSOS_POR_VOLTA;

    char json[200];
    if (sensores::montarJson(json, sizeof json, ID_MAQUINA, leitura) > 0 && mqtt.connected()) {
        mqtt.publish(topicoTelemetria, json);
    }
    Serial.println(json);
}
