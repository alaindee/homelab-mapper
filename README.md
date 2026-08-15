# homelab-map

A self-hosted network/service inventory map. Shows every host in your
homelab (Ubuntu server, Raspberry Pis, Mac Mini, whatever else) as a
hub-and-spoke diagram — click a host to see what's running on it, plus live
CPU/RAM/disk metrics. Toggle to a flat table view of every service across
every host.

Built and tested locally: Portainer auto-sync, manual host/service
creation, agent-token metrics ingestion, stale-container cleanup on
re-sync, and invalid-token rejection were all verified against a running
instance before shipping this.

## How it gets its data

1. **Portainer auto-sync** — configure one or more Portainer instances, and
   every environment (Ubuntu server, any Pi running the Portainer agent)
   becomes a host, every container becomes a service, refreshed every 2
   minutes automatically.
2. **Manual entries** — for anything without Portainer: bare-metal services
   on a Pi, apps on your Mac Mini, network gear, etc.
3. **Metrics agent** — a small shell script you drop on each host (Linux,
   Pi, or Mac) that pushes CPU/RAM/disk/uptime every minute via cron.

## Running it

```bash
mkdir -p volumes/homelab-map
docker compose up -d --build
```

Visit `http://your-homelab-ip:5000`. With nothing configured yet, you'll
see demo data (clearly labeled) so it's never a blank page.

## Adding a Portainer instance to auto-sync

**Get a Portainer API key first:** Portainer UI → your user icon → **My
Account** → **Access Tokens** → **Add access token**.

Then register it with homelab-map:
```bash
curl -X POST http://your-homelab-ip:5000/api/portainer-endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "name": "ubumaster",
    "base_url": "https://your-homelab-ip:9443",
    "api_key": "your_portainer_api_key"
  }'
```

It'll sync within 2 minutes automatically, or trigger it immediately:
```bash
curl -X POST http://your-homelab-ip:5000/api/portainer-endpoints/sync-now
```

If you manage multiple physical machines through **one** Portainer
instance (using the Portainer Agent on each), you only need to register
that one Portainer instance here — it already knows about all of them as
separate "environments," and each becomes its own host automatically.

## Adding a manual host (no Portainer involved)

```bash
curl -X POST http://your-homelab-ip:5000/api/hosts \
  -H "Content-Type: application/json" \
  -d '{
    "name": "raspberrypi-1",
    "type": "raspberry_pi",
    "ip": "192.168.4.140",
    "description": "Pi-hole + network monitoring"
  }'
```
`type` can be `linux`, `raspberry_pi`, `mac`, or `other`. The response
includes the new host's `id` and `agent_token` — save both.

## Adding a manual service to that host

```bash
curl -X POST http://your-homelab-ip:5000/api/services \
  -H "Content-Type: application/json" \
  -d '{
    "host_id": "the_host_id_from_above",
    "name": "pi-hole",
    "port": 80,
    "url": "http://192.168.4.140/admin"
  }'
```

## Enabling metrics for a host

**1. Get the host's agent token** (issued when the host was created,
manually or via Portainer sync):
```bash
curl http://your-homelab-ip:5000/api/hosts/<host_id>/agent-token
```

**2. Copy the right script onto that host:**
- Linux / Raspberry Pi: `agent/report-metrics-linux.sh`
- macOS (e.g. Mac Mini): `agent/report-metrics-mac.sh`

**3. Edit the two variables at the top** of the script:
```bash
HOMELAB_MAP_URL="http://your-homelab-ip:5000"
AGENT_TOKEN="the_token_from_step_1"
```

**4. Make it executable and add to cron**, running every minute:
```bash
chmod +x report-metrics-linux.sh
crontab -e
# add this line:
* * * * * /path/to/report-metrics-linux.sh >> /path/to/homelab-map-agent.log 2>&1
```
Point the log at somewhere in your own home directory, not `/var/log` —
cron runs this as your regular user, and `/var/log` needs root, so that
redirect fails silently and you get no log at all.

(On macOS, `crontab -e` works the same way; you may need to grant cron/
Terminal "Full Disk Access" in System Settings → Privacy & Security for the
disk usage check to work correctly.)

Metrics should appear in the host's side panel within a minute.

## Known limitations (current version)

- **No admin UI yet for adding hosts/services/Portainer endpoints** — all
  of that goes through the API directly via `curl`, as shown above. This is
  the most obvious next thing to build if you want to hand this to
  non-technical housemates/roommates, but for a homelab admin managing
  their own infrastructure, the curl commands above are a one-time setup
  per host.
- **No authentication on the web UI itself** — anyone who can reach port
  5000 can view (and, via the API, modify) the inventory. Fine on a
  trusted LAN; if exposing via Cloudflare Tunnel, put it behind Cloudflare
  Access (or similar) rather than leaving it open.
- **Metrics history isn't kept** — only the latest snapshot per host is
  stored, no historical graphs. Fine for "is this thing healthy right now,"
  not a replacement for a real monitoring stack (Netdata/Beszel) if you
  want trends over time.
- **Diagram layout is a simple circle** — fine for a handful of hosts;
  would need a smarter layout algorithm if this grows to dozens of hosts.

## Sharing this with other homelabers

If you want to open-source this, worth adding before publishing:
- A simple auth layer (even basic HTTP auth would cover most homelab needs)
- A basic settings page in the UI for the host/service/Portainer-endpoint
  management, instead of requiring curl
- Environment-variable-based initial admin token instead of an open API

The core data model (hosts → services, Portainer-sourced or manual, plus a
lightweight cross-platform metrics agent) is the reusable part — the gaps
above are mostly UI/polish, not architecture.
