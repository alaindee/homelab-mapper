"""
demo_data.py - shown automatically when no real hosts have been added yet,
so the UI is never a blank page on first run.
"""

import time

_NOW = time.time()


def get_demo_map() -> dict:
    return {
        "demo": True,
        "hosts": [
            {
                "id": "demo-ubuntu",
                "name": "ubumaster (Ubuntu Server)",
                "type": "linux",
                "ip": "192.168.4.117",
                "description": "Main homelab server - Docker host",
                "source": "portainer",
                "services": [
                    {"id": "d1", "name": "mattermost", "type": "docker", "status": "running", "port": 8065, "url": None, "notes": None},
                    {"id": "d2", "name": "gitea", "type": "docker", "status": "running", "port": 3000, "url": None, "notes": None},
                    {"id": "d3", "name": "duplicati", "type": "docker", "status": "running", "port": 8200, "url": None, "notes": None},
                    {"id": "d4", "name": "portainer", "type": "docker", "status": "running", "port": 9000, "url": None, "notes": None},
                ],
                "metrics": {"cpu_pct": 18.4, "mem_pct": 61.2, "disk_pct": 47.0, "uptime_seconds": 863000, "updated_at": _NOW},
            },
            {
                "id": "demo-pi1",
                "name": "raspberrypi-1",
                "type": "raspberry_pi",
                "ip": "192.168.4.140",
                "description": "Pi-hole + network monitoring",
                "source": "manual",
                "services": [
                    {"id": "d5", "name": "pi-hole", "type": "manual", "status": "running", "port": 80, "url": "http://192.168.4.140/admin", "notes": "DNS ad-blocking"},
                ],
                "metrics": {"cpu_pct": 4.1, "mem_pct": 22.0, "disk_pct": 12.5, "uptime_seconds": 1500000, "updated_at": _NOW},
            },
            {
                "id": "demo-mac",
                "name": "Mac Mini",
                "type": "mac",
                "ip": "192.168.4.150",
                "description": "Media server",
                "source": "manual",
                "services": [
                    {"id": "d6", "name": "Plex", "type": "manual", "status": "running", "port": 32400, "url": None, "notes": None},
                ],
                "metrics": {"cpu_pct": 9.8, "mem_pct": 40.3, "disk_pct": 71.2, "uptime_seconds": 400000, "updated_at": _NOW},
            },
        ],
    }


def get_demo_table() -> dict:
    demo_map = get_demo_map()
    services = []
    for host in demo_map["hosts"]:
        for s in host["services"]:
            services.append({**s, "host_name": host["name"], "host_type": host["type"]})
    return {"demo": True, "services": services}
