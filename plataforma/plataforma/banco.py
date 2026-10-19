"""Acesso ao PostgreSQL/TimescaleDB com psycopg 3 assíncrono."""

from datetime import datetime
from importlib import resources

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from plataforma.alertas import Evento, TipoAlerta
from plataforma.modelos import Leitura


class Repositorio:
    def __init__(self, url: str):
        self.pool = AsyncConnectionPool(
            url, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row}
        )

    async def abrir(self) -> None:
        await self.pool.open(wait=True)
        sql = resources.files("plataforma").joinpath("banco.sql").read_text(encoding="utf-8")
        async with self.pool.connection() as conn:
            await conn.execute(sql)

    async def fechar(self) -> None:
        await self.pool.close()

    async def registrar(self, leitura: Leitura) -> dict:
        """Grava a leitura (cadastrando a máquina na primeira vez) e devolve os limites dela."""
        async with self.pool.connection() as conn:
            maquina = await (
                await conn.execute(
                    """
                    INSERT INTO maquinas (id, nome, online, visto_em) VALUES (%(id)s, %(id)s, true, %(tempo)s)
                    ON CONFLICT (id) DO UPDATE SET online = true, visto_em = EXCLUDED.visto_em
                    RETURNING id, limite_temperatura_c, limite_vibracao_g
                    """,
                    {"id": leitura.maquina, "tempo": leitura.instante()},
                )
            ).fetchone()
            await conn.execute(
                """
                INSERT INTO leituras (tempo, maquina_id, temperatura_c, vibracao_rms_g, corrente_a, rpm)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    leitura.instante(),
                    leitura.maquina,
                    leitura.temperatura_c,
                    leitura.vibracao_rms_g,
                    leitura.corrente_a,
                    leitura.rpm,
                ),
            )
        return maquina

    async def registrar_evento(self, evento: Evento, quando: datetime) -> None:
        async with self.pool.connection() as conn:
            if evento.abriu:
                await conn.execute(
                    """
                    INSERT INTO alertas (maquina_id, tipo, valor, limite, inicio) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (maquina_id, tipo) WHERE fim IS NULL DO NOTHING
                    """,
                    (evento.maquina, evento.tipo.value, evento.valor, evento.limite, quando),
                )
            else:
                await conn.execute(
                    "UPDATE alertas SET fim = %s WHERE maquina_id = %s AND tipo = %s AND fim IS NULL",
                    (quando, evento.maquina, evento.tipo.value),
                )

    async def definir_online(self, maquina: str, online: bool) -> None:
        async with self.pool.connection() as conn:
            await conn.execute("UPDATE maquinas SET online = %s WHERE id = %s", (online, maquina))

    async def alertas_abertos(self) -> list[tuple[str, TipoAlerta]]:
        async with self.pool.connection() as conn:
            linhas = await (
                await conn.execute("SELECT maquina_id, tipo FROM alertas WHERE fim IS NULL")
            ).fetchall()
        return [(linha["maquina_id"], TipoAlerta(linha["tipo"])) for linha in linhas]

    async def maquinas(self) -> list[dict]:
        """Cada máquina com a última leitura e a quantidade de alertas abertos."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT m.*, u.temperatura_c, u.vibracao_rms_g, u.corrente_a, u.rpm,
                       (SELECT count(*) FROM alertas a
                         WHERE a.maquina_id = m.id AND a.fim IS NULL) AS alertas_abertos
                  FROM maquinas m
                  LEFT JOIN LATERAL (
                      SELECT * FROM leituras l WHERE l.maquina_id = m.id ORDER BY l.tempo DESC LIMIT 1
                  ) u ON true
                 ORDER BY m.id
                """
            )
            return await cursor.fetchall()

    async def maquina(self, maquina_id: str) -> dict | None:
        async with self.pool.connection() as conn:
            cursor = await conn.execute("SELECT * FROM maquinas WHERE id = %s", (maquina_id,))
            return await cursor.fetchone()

    async def definir_limites(self, maquina_id: str, temperatura: float, vibracao: float) -> dict | None:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                UPDATE maquinas SET limite_temperatura_c = %s, limite_vibracao_g = %s
                 WHERE id = %s RETURNING *
                """,
                (temperatura, vibracao, maquina_id),
            )
            return await cursor.fetchone()

    async def historico(self, maquina_id: str, minutos: int, segundos_por_ponto: int) -> list[dict]:
        """Médias e máximos por intervalo (date_bin funciona no PostgreSQL puro e no TimescaleDB)."""
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT date_bin(make_interval(secs => %(passo)s), tempo, timestamptz '2000-01-01') AS tempo,
                       round(avg(temperatura_c)::numeric, 2)::float  AS temperatura_c,
                       round(max(vibracao_rms_g)::numeric, 3)::float AS vibracao_rms_g,
                       round(avg(corrente_a)::numeric, 2)::float     AS corrente_a,
                       round(avg(rpm)::numeric, 0)::float            AS rpm
                  FROM leituras
                 WHERE maquina_id = %(maquina)s AND tempo > now() - make_interval(mins => %(minutos)s)
                 GROUP BY 1
                 ORDER BY 1
                """,
                {"maquina": maquina_id, "minutos": minutos, "passo": segundos_por_ponto},
            )
            return await cursor.fetchall()

    async def alertas(self, apenas_abertos: bool, limite: int = 50) -> list[dict]:
        async with self.pool.connection() as conn:
            cursor = await conn.execute(
                f"""
                SELECT * FROM alertas {"WHERE fim IS NULL" if apenas_abertos else ""}
                 ORDER BY inicio DESC LIMIT %s
                """,
                (limite,),
            )
            return await cursor.fetchall()
