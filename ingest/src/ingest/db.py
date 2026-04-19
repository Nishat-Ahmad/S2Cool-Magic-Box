"""Neon Serverless PostgreSQL integration (schema init & batch UPSERT)."""

from __future__ import annotations

import logging
from collections.abc import Generator, Sequence
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as pgconnection

from .api import SolarWeatherRecord

logger = logging.getLogger(__name__)


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS solar_weather_data (
    id                          BIGSERIAL,
    city_name                   VARCHAR(100)  NOT NULL,
    timestamp                   TIMESTAMPTZ   NOT NULL,
    temperature_2m              FLOAT,
    relative_humidity_2m        FLOAT,
    wind_speed_10m              FLOAT,
    cloud_cover                 FLOAT,
    shortwave_radiation         FLOAT,
    direct_radiation            FLOAT,
    direct_normal_irradiance    FLOAT,
    diffuse_radiation           FLOAT,
    ingested_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT pk_solar_weather PRIMARY KEY (city_name, timestamp)
);
"""

UPSERT_SQL = """
INSERT INTO solar_weather_data (
    city_name, timestamp,
    temperature_2m, relative_humidity_2m, wind_speed_10m, cloud_cover,
    shortwave_radiation, direct_radiation, direct_normal_irradiance, diffuse_radiation
)
VALUES %s
ON CONFLICT (city_name, timestamp)
DO UPDATE SET
    temperature_2m           = EXCLUDED.temperature_2m,
    relative_humidity_2m     = EXCLUDED.relative_humidity_2m,
    wind_speed_10m           = EXCLUDED.wind_speed_10m,
    cloud_cover              = EXCLUDED.cloud_cover,
    shortwave_radiation      = EXCLUDED.shortwave_radiation,
    direct_radiation         = EXCLUDED.direct_radiation,
    direct_normal_irradiance = EXCLUDED.direct_normal_irradiance,
    diffuse_radiation        = EXCLUDED.diffuse_radiation,
    ingested_at              = NOW();
"""


@contextmanager
def get_connection(database_url: str) -> Generator[pgconnection, None, None]:
    """Yield a psycopg2 connection with auto-commit/rollback semantics.

    Args:
        database_url: libpq-compatible DSN (Neon requires ``sslmode=require``).
    """
    conn: pgconnection | None = None
    try:
        conn = psycopg2.connect(database_url)
        yield conn
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        raise
    finally:
        if conn is not None:
            conn.close()


def init_db(database_url: str) -> None:
    """Create ``solar_weather_data`` table if it doesn't exist (idempotent)."""
    logger.info("Initialising database schema.")
    with get_connection(database_url) as conn, conn.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)


def upsert_records(
    database_url: str,
    records: Sequence[SolarWeatherRecord],
    city_name: str = "",
) -> None:
    """Batch-upsert records via ``execute_values``.

    Args:
        database_url: Postgres DSN.
        records: ``SolarWeatherRecord`` instances to persist.
        city_name: Label for log messages when *records* may be empty.
    """
    if not records:
        logger.info("[%s] Nothing to upsert.", city_name)
        return

    label = records[0].city_name
    rows = [
        (
            r.city_name,
            r.timestamp,
            r.temperature_2m,
            r.relative_humidity_2m,
            r.wind_speed_10m,
            r.cloud_cover,
            r.shortwave_radiation,
            r.direct_radiation,
            r.direct_normal_irradiance,
            r.diffuse_radiation,
        )
        for r in records
    ]
    logger.info("[%s] Upserting %d records.", label, len(rows))

    with get_connection(database_url) as conn, conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, UPSERT_SQL, rows, page_size=500)
        logger.info("[%s] Upsert complete — %s", label, cur.statusmessage)
