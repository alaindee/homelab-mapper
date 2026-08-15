"""
app.py - homelab-map

A self-hosted network/service inventory map. Combines:
  - Auto-discovered hosts + containers from one or more Portainer instances
  - Manually catalogued hosts/services for anything without Portainer
    (bare-metal Pi services, Mac Mini apps, network gear, etc.)
  - Basic health metrics pushed by a small agent script on each host

Single-page vanilla JS/CSS frontend, no build step - matches the project's
other homelab tools.
"""

import logging
import threading
import time

from flask import Flask, jsonify, render_template, request

import db
import demo_data
import portainer_sync

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("homelab-map")

app = Flask(__name__)

db.init_db()

SYNC_INTERVAL_SECONDS = 120


# ---------------------------------------------------------------------------
# Background Portainer sync loop
# ---------------------------------------------------------------------------


def _sync_loop():
    while True:
        try:
            conn = db.get_conn()
            results = portainer_sync.sync_all(conn)
            conn.close()
            if results:
                logger.info("Portainer sync: %s", results)
        except Exception:
            logger.exception("Portainer sync loop error")
        time.sleep(SYNC_INTERVAL_SECONDS)


threading.Thread(target=_sync_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Hosts + services (combined "map" view)
# ---------------------------------------------------------------------------


@app.route("/api/map")
def api_map():
    """Returns everything the frontend needs in one call: hosts, their
    services, latest metrics, and whether we're serving live or demo data."""
    conn = db.get_conn()
    hosts = db.list_hosts(conn)

    if not hosts:
        conn.close()
        return jsonify(demo_data.get_demo_map())

    result = []
    for host in hosts:
        services = db.list_services_for_host(conn, host["id"])
        metrics = db.get_metrics(conn, host["id"])
        result.append(
            {
                "id": host["id"],
                "name": host["name"],
                "type": host["type"],
                "ip": host["ip"],
                "description": host["description"],
                "source": host["source"],
                "services": [
                    {
                        "id": s["id"],
                        "name": s["name"],
                        "type": s["type"],
                        "status": s["status"],
                        "port": s["port"],
                        "url": s["url"],
                        "notes": s["notes"],
                    }
                    for s in services
                ],
                "metrics": metrics
                and {
                    "cpu_pct": metrics["cpu_pct"],
                    "mem_pct": metrics["mem_pct"],
                    "disk_pct": metrics["disk_pct"],
                    "uptime_seconds": metrics["uptime_seconds"],
                    "updated_at": metrics["updated_at"],
                },
            }
        )
    conn.close()
    return jsonify({"demo": False, "hosts": result})


@app.route("/api/table")
def api_table():
    """Flat list of every service across every host, for the table view."""
    conn = db.get_conn()
    hosts = db.list_hosts(conn)
    if not hosts:
        conn.close()
        return jsonify(demo_data.get_demo_table())
    services = db.list_all_services(conn)
    conn.close()
    return jsonify({"demo": False, "services": services})


# ---------------------------------------------------------------------------
# Manual host management
# ---------------------------------------------------------------------------


@app.route("/api/hosts", methods=["POST"])
def api_create_host():
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    conn = db.get_conn()
    host_id = db.create_manual_host(
        conn,
        name=name,
        type_=payload.get("type", "linux"),
        ip=payload.get("ip"),
        description=payload.get("description"),
    )
    conn.commit()
    host = db.get_host(conn, host_id)
    conn.close()
    return jsonify(host), 201


@app.route("/api/hosts/<host_id>", methods=["DELETE"])
def api_delete_host(host_id):
    conn = db.get_conn()
    db.delete_host(conn, host_id)
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/hosts/<host_id>/agent-token")
def api_get_agent_token(host_id):
    """Returns the token this host's metrics agent script should use."""
    conn = db.get_conn()
    host = db.get_host(conn, host_id)
    conn.close()
    if not host:
        return jsonify({"error": "not found"}), 404
    return jsonify({"agent_token": host["agent_token"]})


# ---------------------------------------------------------------------------
# Manual service management
# ---------------------------------------------------------------------------


@app.route("/api/services", methods=["POST"])
def api_create_service():
    payload = request.get_json(force=True)
    host_id = payload.get("host_id")
    name = (payload.get("name") or "").strip()
    if not host_id or not name:
        return jsonify({"error": "host_id and name are required"}), 400

    conn = db.get_conn()
    if not db.get_host(conn, host_id):
        conn.close()
        return jsonify({"error": "host not found"}), 404

    service_id = db.create_manual_service(
        conn,
        host_id=host_id,
        name=name,
        port=payload.get("port"),
        url=payload.get("url"),
        notes=payload.get("notes"),
    )
    conn.commit()
    conn.close()
    return jsonify({"id": service_id}), 201


@app.route("/api/services/<service_id>", methods=["DELETE"])
def api_delete_service(service_id):
    conn = db.get_conn()
    db.delete_service(conn, service_id)
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/services/<service_id>/status", methods=["PUT"])
def api_update_service_status(service_id):
    payload = request.get_json(force=True)
    status = payload.get("status")
    if status not in ("running", "stopped", "unknown"):
        return jsonify({"error": "status must be running, stopped, or unknown"}), 400
    conn = db.get_conn()
    db.update_service_status(conn, service_id, status)
    conn.commit()
    conn.close()
    return "", 204


# ---------------------------------------------------------------------------
# Metrics agent endpoint (called by the small script on each host)
# ---------------------------------------------------------------------------


@app.route("/api/metrics", methods=["POST"])
def api_post_metrics():
    token = request.headers.get("X-Agent-Token")
    if not token:
        return jsonify({"error": "missing X-Agent-Token header"}), 401

    conn = db.get_conn()
    host = db.find_host_by_agent_token(conn, token)
    if not host:
        conn.close()
        return jsonify({"error": "invalid agent token"}), 403

    payload = request.get_json(force=True)
    db.upsert_metrics(
        conn,
        host_id=host["id"],
        cpu_pct=payload.get("cpu_pct"),
        mem_pct=payload.get("mem_pct"),
        disk_pct=payload.get("disk_pct"),
        uptime_seconds=payload.get("uptime_seconds"),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Portainer endpoint management (configure which Portainer instances to sync)
# ---------------------------------------------------------------------------


@app.route("/api/portainer-endpoints", methods=["GET"])
def api_list_portainer_endpoints():
    conn = db.get_conn()
    endpoints = db.list_portainer_endpoints(conn)
    conn.close()
    # never return api keys to the frontend
    for e in endpoints:
        e.pop("api_key", None)
    return jsonify(endpoints)


@app.route("/api/portainer-endpoints", methods=["POST"])
def api_create_portainer_endpoint():
    payload = request.get_json(force=True)
    name = (payload.get("name") or "").strip()
    base_url = (payload.get("base_url") or "").strip()
    api_key = (payload.get("api_key") or "").strip()
    if not name or not base_url or not api_key:
        return jsonify({"error": "name, base_url, and api_key are required"}), 400

    conn = db.get_conn()
    endpoint_id = db.create_portainer_endpoint(conn, name, base_url, api_key)
    conn.commit()
    conn.close()
    return jsonify({"id": endpoint_id}), 201


@app.route("/api/portainer-endpoints/<endpoint_id>", methods=["DELETE"])
def api_delete_portainer_endpoint(endpoint_id):
    conn = db.get_conn()
    db.delete_portainer_endpoint(conn, endpoint_id)
    conn.commit()
    conn.close()
    return "", 204


@app.route("/api/portainer-endpoints/sync-now", methods=["POST"])
def api_sync_now():
    conn = db.get_conn()
    results = portainer_sync.sync_all(conn)
    conn.close()
    return jsonify({"results": results})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
