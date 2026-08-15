#!/bin/bash
# report-metrics-mac.sh
#
# Reads CPU/RAM/disk/uptime on macOS (e.g. a Mac Mini) and pushes them to
# homelab-map. macOS has no /proc, so this uses top, vm_stat, and sysctl.
#
# Usage: set the two variables below, then add to cron or a launchd job,
# e.g. every minute via `crontab -e`:
#   * * * * * /path/to/report-metrics-mac.sh >> /tmp/homelab-map-agent.log 2>&1

set -eu

HOMELAB_MAP_URL="http://192.168.4.117:5000"
AGENT_TOKEN="paste_this_hosts_agent_token_here"

# CPU % - macOS `top` reports idle % directly in one sample
idle_pct=$(top -l 1 -n 0 | awk -F'[,:%]' '/CPU usage/ {for(i=1;i<=NF;i++) if ($i ~ /idle/) print $(i-1)}' | tr -d ' ')
cpu_pct=$(awk -v idle="$idle_pct" 'BEGIN { printf "%.1f", 100 - idle }')

# Memory % via vm_stat (page size * pages, free vs used)
page_size=$(vm_stat | head -1 | grep -o '[0-9]*')
pages_free=$(vm_stat | awk '/Pages free/ {gsub("\\.",""); print $3}')
pages_active=$(vm_stat | awk '/Pages active/ {gsub("\\.",""); print $3}')
pages_inactive=$(vm_stat | awk '/Pages inactive/ {gsub("\\.",""); print $3}')
pages_wired=$(vm_stat | awk '/Pages wired down/ {gsub("\\.",""); print $4}')

total_pages=$(( pages_free + pages_active + pages_inactive + pages_wired ))
used_pages=$(( pages_active + pages_inactive + pages_wired ))
mem_pct=$(awk -v u="$used_pages" -v t="$total_pages" 'BEGIN { printf "%.1f", (u/t) * 100 }')

# Disk % (root volume)
disk_pct=$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')

# Uptime in seconds
boot_epoch=$(sysctl -n kern.boottime | awk -F'[ ,]+' '{print $4}')
now_epoch=$(date +%s)
uptime_seconds=$(( now_epoch - boot_epoch ))

curl -s -X POST "${HOMELAB_MAP_URL}/api/metrics" \
  -H "Content-Type: application/json" \
  -H "X-Agent-Token: ${AGENT_TOKEN}" \
  -d "{\"cpu_pct\": ${cpu_pct}, \"mem_pct\": ${mem_pct}, \"disk_pct\": ${disk_pct}, \"uptime_seconds\": ${uptime_seconds}}" \
  -o /dev/null -w "homelab-map agent: HTTP %{http_code}\n"
