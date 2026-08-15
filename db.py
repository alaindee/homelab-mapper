"""
db.py - SQLite schema + data access for homelab-map.

Kept intentionally simple (no ORM) to match the project's philosophy:
single-file, easy to inspect/back up, no build step.
"""

import sqlite3
import time
import uuid
from pathlib import Path

DB_PATH = Path("/tmp/homelab_data/homelab.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS hosts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'linux',   -- linux | raspberry_pi | mac | other
    ip TEXT,
    description TEXT,
    source TEXT NOT NULL DEFAULT 'manual', -- manual | portainer
    portainer_environment_id INTEGER,
    agent_token TEXT,                      -- required for metrics agent auth
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS services (
    id TEXT PRIMARY KEY,
    host_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'manual',   -- docker | manual
    status TEXT NOT NULL DEFAULT 'unknown', -- running | stopped | unknown
    port INTEGER,
    url TEXT,
    container_id TEXT,                     -- set when type = docker
    notes TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS metrics (
    host_id TEXT PRIMARY KEY REFERENCES hosts(id) ON DELETE CASCADE,
    cpu_pct REAL,
    mem_pct REAL,
    disk_pct REAL,
    uptime_seconds INTEGER,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS portainer_endpoints (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    created_at REAL NOT NULL
);
"""


def get_conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> float:
    return time.time()


# --- hosts -----------------------------------------------------------

def list_hosts(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM hosts ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def get_host(conn, host_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM hosts WHERE id = ?", (host_id,)).fetchone()
    return dict(row) if row else None


def upsert_host_by_source(conn, name, type_, ip, description, source, portainer_environment_id=None) -> str:
    """Used by the Portainer sync - finds an existing host for this
    environment, or creates one, keyed on (source, portainer_environment_id)."""
    if source == "portainer" and portainer_environment_id is not None:
        row = conn.execute(
            "SELECT id FROM hosts WHERE source = 'portainer' AND portainer_environment_id = ?",
            (portainer_environment_id,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE hosts SET name = ?, ip = ?, description = ? WHERE id = ?",
                (name, ip, description, row["id"]),
            )
            return row["id"]

    host_id = new_id()
    conn.execute(
        """INSERT INTO hosts (id, name, type, ip, description, source, portainer_environment_id, agent_token, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (host_id, name, type_, ip, description, source, portainer_environment_id, new_id(), now()),
    )
    return host_id


def create_manual_host(conn, name, type_, ip, description) -> str:
    host_id = new_id()
    conn.execute(
        """INSERT INTO hosts (id, name, type, ip, description, source, agent_token, created_at)
           VALUES (?, ?, ?, ?, ?, 'manual', ?, ?)""",
        (host_id, name, type_, ip, description, new_id(), now()),
    )
    return host_id


def delete_host(conn, host_id: str) -> None:
    conn.execute("DELETE FROM hosts WHERE id = ?", (host_id,))


def find_host_by_agent_token(conn, token: str) -> dict | None:
    row = conn.execute("SELECT * FROM hosts WHERE agent_token = ?", (token,)).fetchone()
    return dict(row) if row else None


# --- services ----------------------------------------------------------

def list_services_for_host(conn, host_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM services WHERE host_id = ? ORDER BY name", (host_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_all_services(conn) -> list[dict]:
    rows = conn.execute(
        """SELECT services.*, hosts.name AS host_name, hosts.type AS host_type
           FROM services JOIN hosts ON services.host_id = hosts.id
           ORDER BY hosts.name, services.name"""
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_docker_service(conn, host_id, container_id, name, status, port) -> None:
    row = conn.execute(
        "SELECT id FROM services WHERE host_id = ? AND container_id = ?",
        (host_id, container_id),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE services SET name = ?, status = ?, port = ?, updated_at = ? WHERE id = ?",
            (name, status, port, now(), row["id"]),
        )
    else:
        conn.execute(
            """INSERT INTO services (id, host_id, name, type, status, port, container_id, created_at, updated_at)
               VALUES (?, ?, ?, 'docker', ?, ?, ?, ?, ?)""",
            (new_id(), host_id, name, status, port, container_id, now(), now()),
        )


def remove_stale_docker_services(conn, host_id: str, seen_container_ids: set[str]) -> None:
    """Removes docker-sourced services no longer reported by Portainer for this host."""
    rows = conn.execute(
        "SELECT id, container_id FROM services WHERE host_id = ? AND type = 'docker'",
        (host_id,),
    ).fetchall()
    for r in rows:
        if r["container_id"] not in seen_container_ids:
            conn.execute("DELETE FROM services WHERE id = ?", (r["id"],))


def create_manual_service(conn, host_id, name, port, url, notes) -> str:
    service_id = new_id()
    conn.execute(
        """INSERT INTO services (id, host_id, name, type, status, port, url, notes, created_at, updated_at)
           VALUES (?, ?, ?, 'manual', 'unknown', ?, ?, ?, ?, ?)""",
        (service_id, host_id, name, port, url, notes, now(), now()),
    )
    return service_id


def delete_service(conn, service_id: str) -> None:
    conn.execute("DELETE FROM services WHERE id = ?", (service_id,))


def update_service_status(conn, service_id: str, status: str) -> None:
    conn.execute("UPDATE services SET status = ?, updated_at = ? WHERE id = ?", (status, now(), service_id))


# --- metrics -----------------------------------------------------------

def upsert_metrics(conn, host_id, cpu_pct, mem_pct, disk_pct, uptime_seconds) -> None:
    conn.execute(
        """INSERT INTO metrics (host_id, cpu_pct, mem_pct, disk_pct, uptime_seconds, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(host_id) DO UPDATE SET
             cpu_pct = excluded.cpu_pct,
             mem_pct = excluded.mem_pct,
             disk_pct = excluded.disk_pct,
             uptime_seconds = excluded.uptime_seconds,
             updated_at = excluded.updated_at""",
        (host_id, cpu_pct, mem_pct, disk_pct, uptime_seconds, now()),
    )


def get_metrics(conn, host_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM metrics WHERE host_id = ?", (host_id,)).fetchone()
    return dict(row) if row else None


# --- portainer endpoints ------------------------------------------------

def list_portainer_endpoints(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM portainer_endpoints ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_portainer_endpoint(conn, name, base_url, api_key) -> str:
    endpoint_id = new_id()
    conn.execute(
        "INSERT INTO portainer_endpoints (id, name, base_url, api_key, created_at) VALUES (?, ?, ?, ?, ?)",
        (endpoint_id, name, base_url.rstrip("/"), api_key, now()),
    )
    return endpoint_id


def delete_portainer_endpoint(conn, endpoint_id: str) -> None:
    conn.execute("DELETE FROM portainer_endpoints WHERE id = ?", (endpoint_id,))
