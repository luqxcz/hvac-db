#!/usr/bin/env python3

"""
Local test script for the HVAC heartbeat Lambda function.
This exercises the handler against your database using env vars
mirroring alembic.ini settings.
"""

import os
import json
from datetime import datetime
import psycopg2

from lambda_function import lambda_handler


def set_env_from_alembic_defaults() -> None:
    # Adjust DB_PASSWORD to your actual local password if different
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_PORT", "55432")
    os.environ.setdefault("DB_NAME", "hvacdb")
    os.environ.setdefault("DB_USER", "postgres")
    os.environ.setdefault("DB_PASSWORD", "yourpassword")


def check_connection() -> bool:
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ["DB_PORT"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
            print(f"Connected to PostgreSQL: {version}")
        conn.close()
        return True
    except Exception as exc:
        print(f"Connection failed: {exc}")
        return False


def ensure_tables_present() -> bool:
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ["DB_PORT"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = 'device_state'
                );
                """
            )
            exists = cur.fetchone()[0]
            if not exists:
                print("Table 'device_state' not found. Run alembic upgrade head.")
                return False
        conn.close()
        return True
    except Exception as exc:
        print(f"Error checking tables: {exc}")
        return False


def query_device_state() -> None:
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ["DB_PORT"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT device_id, site_id, last_seen_ts, status
                FROM device_state
                ORDER BY last_seen_ts DESC NULLS LAST;
                """
            )
            rows = cur.fetchall()
            print("\nCurrent device_state rows:")
            for r in rows:
                print(" -", r)

            try:
                cur.execute(
                    """
                    SELECT device_id, site_id, last_seen_ts, now() - last_seen_ts AS age
                    FROM v_devices_stale
                    ORDER BY age DESC;
                    """
                )
                vrows = cur.fetchall()
                print("\nStale devices (>120s):")
                if vrows:
                    for r in vrows:
                        print(" -", r)
                else:
                    print(" - none")
            except Exception as exc2:
                print(f"Note: could not query v_devices_stale: {exc2}")
        conn.close()
    except Exception as exc:
        print(f"Query failed: {exc}")


def seed_site_and_devices() -> None:
    """Insert required site and devices for tests if missing."""
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ["DB_PORT"],
            database=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
        )
        with conn.cursor() as cur:
            # Ensure site exists
            cur.execute(
                """
                INSERT INTO sites (site_id, display_name)
                VALUES (%s, %s)
                ON CONFLICT (site_id) DO NOTHING;
                """,
                ("test-building", "Test Building"),
            )

            # Ensure devices exist
            for device_id in ("hvac-test-001", "hvac-test-002", "hvac-test-003"):
                cur.execute(
                    """
                    INSERT INTO devices (device_id, site_id, model)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (device_id) DO NOTHING;
                    """,
                    (device_id, "test-building", "test-model"),
                )
        conn.commit()
        conn.close()
        print("Seeded required site/devices (if missing).")
    except Exception as exc:
        print(f"Seeding failed: {exc}")


def run_tests() -> None:
    single_event = {
        "device_id": "hvac-test-001",
        "site_id": "test-building",
        "status": "ready",
        "agent_version": "1.0.0",
        "cpu_pct": 23.4,
        "disk_free_gb": 99.1,
    }
    print("\nInvoking handler (single device)...")
    res = lambda_handler(single_event, None)
    print(json.dumps(res, indent=2))

    batch_event = {
        "devices": [
            {"device_id": "hvac-test-002", "site_id": "test-building", "status": "ready", "cpu_pct": 12.2},
            {"device_id": "hvac-test-003", "site_id": "test-building", "status": "degraded", "cpu_pct": 88.7},
        ]
    }
    print("\nInvoking handler (batch)...")
    res = lambda_handler(batch_event, None)
    print(json.dumps(res, indent=2))


def main() -> None:
    set_env_from_alembic_defaults()
    print(
        f"Using DB {os.environ['DB_USER']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )
    if not check_connection():
        return
    if not ensure_tables_present():
        return

    # Seed minimal data required for FK constraints
    seed_site_and_devices()

    print("\nBefore updates:")
    query_device_state()

    run_tests()

    print("\nAfter updates:")
    query_device_state()


if __name__ == "__main__":
    main()


