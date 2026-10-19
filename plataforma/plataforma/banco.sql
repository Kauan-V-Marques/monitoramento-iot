-- Estrutura do banco (idempotente: roda a cada inicialização)

CREATE TABLE IF NOT EXISTS maquinas (
    id                   text PRIMARY KEY,
    nome                 text        NOT NULL,
    limite_temperatura_c real        NOT NULL DEFAULT 80,
    limite_vibracao_g    real        NOT NULL DEFAULT 0.8,
    online               boolean     NOT NULL DEFAULT false,
    visto_em             timestamptz
);

CREATE TABLE IF NOT EXISTS leituras (
    tempo          timestamptz NOT NULL,
    maquina_id     text        NOT NULL REFERENCES maquinas (id),
    temperatura_c  real,
    vibracao_rms_g real        NOT NULL,
    corrente_a     real        NOT NULL,
    rpm            real        NOT NULL
);
CREATE INDEX IF NOT EXISTS leituras_maquina_tempo ON leituras (maquina_id, tempo DESC);

CREATE TABLE IF NOT EXISTS alertas (
    id         bigserial PRIMARY KEY,
    maquina_id text        NOT NULL REFERENCES maquinas (id),
    tipo       text        NOT NULL CHECK (tipo IN ('temperatura', 'vibracao')),
    valor      real        NOT NULL,
    limite     real        NOT NULL,
    inicio     timestamptz NOT NULL,
    fim        timestamptz
);
-- No máximo um alerta aberto por máquina e tipo
CREATE UNIQUE INDEX IF NOT EXISTS alertas_um_aberto ON alertas (maquina_id, tipo) WHERE fim IS NULL;

-- Com TimescaleDB disponível, "leituras" vira uma hypertable (particionada por tempo)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
        CREATE EXTENSION IF NOT EXISTS timescaledb;
        PERFORM create_hypertable('leituras', 'tempo', if_not_exists => true, migrate_data => true);
    END IF;
END
$$;
