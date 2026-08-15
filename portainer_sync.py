"""
portainer_sync.py - pulls environments (endpoints) and containers from one
or more Portainer instances and merges them into the local hosts/services
tables.

Each Portainer "endpoint" (their term for a managed Docker environment -
e.g. your Ubuntu server, or a Pi running the Portainer agent) becomes one
host here. Each container on that endpoint becomes one service.
"""

import logging
import re

import requests

import db

logger = logging.getLogger("homelab-map.portainer")


def _guess_host_type(name: str) -> str:
    name_lower = name.lower()
    if "raspberry" in name_lower or re.search(r"\bpi\b", name_lower):
        return "raspberry_pi"
    if "mac" in name_lower or "mini" in name_lower:
        return "mac"
    return "linux"


def sync_portainer_endpoint(conn, endpoint: dict) -> dict:
    """Syncs one configured Portainer instance. Returns a small summary dict
    for logging/debugging; never raises - failures are reported in the
    summary so one broken endpoint doesn't stop others from syncing."""

    base_url = endpoint["base_url"]
    api_key = endpoint["api_key"]
    headers = {"X-API-Key": api_key}

    summary = {"endpoint": endpoint["name"], "hosts": 0, "services": 0, "errors": []}

    try:
        resp = requests.get(f"{base_url}/api/endpoints", headers=headers, timeout=10)
        resp.raise_for_status()
        environments = resp.json()
    except Exception as exc:
        summary["errors"].append(f"Failed to list environments: {exc}")
        logger.warning("Portainer sync failed for %s: %s", endpoint["name"], exc)
        return summary

    for env in environments:
        env_id = env["Id"]
        env_name = env.get("Name", f"environment-{env_id}")

        host_id = db.upsert_host_by_source(
            conn,
            name=env_name,
            type_=_guess_host_type(env_name),
            ip=env.get("URL", "").replace("tcp://", "").split(":")[0] or None,
            description=f"Auto-synced from Portainer ({endpoint['name']})",
            source="portainer",
            portainer_environment_id=env_id,
        )
        summary["hosts"] += 1

        try:
            containers_resp = requests.get(
                f"{base_url}/api/endpoints/{env_id}/docker/containers/json",
                headers=headers,
                params={"all": "true"},
                timeout=10,
            )
            containers_resp.raise_for_status()
            containers = containers_resp.json()
        except Exception as exc:
            summary["errors"].append(f"Failed to list containers for {env_name}: {exc}")
            logger.warning("Failed to list containers for %s: %s", env_name, exc)
            continue

        seen_container_ids = set()
        for c in containers:
            container_id = c["Id"]
            seen_container_ids.add(container_id)
            name = (c.get("Names") or ["/unknown"])[0].lstrip("/")
            status = "running" if c.get("State") == "running" else "stopped"
            port = None
            ports = c.get("Ports") or []
            for p in ports:
                if p.get("PublicPort"):
                    port = p["PublicPort"]
                    break

            db.upsert_docker_service(conn, host_id, container_id, name, status, port)
            summary["services"] += 1

        db.remove_stale_docker_services(conn, host_id, seen_container_ids)

    conn.commit()
    return summary


def sync_all(conn) -> list[dict]:
    endpoints = db.list_portainer_endpoints(conn)
    return [sync_portainer_endpoint(conn, ep) for ep in endpoints]
