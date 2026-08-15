#!/bin/bash
# report-metrics-linux.sh
#
# Reads CPU/RAM/disk/uptime from /proc and pushes them to homelab-map.
# Works on any standard Linux, including Raspberry Pi OS.
#
# Usage: set the two variables below, then add to cron, e.g. every minute:
#   * * * * * /path/to/report-metrics-linux.sh >> /var/log/homelab-map-agent.log 2>&1

set -eu

HOMELAB_MAP_URL="http://192.168.4.117:5000"   # where homelab-map is reachable
AGENT_TOKEN="paste_this_hosts_agent_token_here"

# CPU % - average over a 1-second sample
read -r cpu_line1 < /proc/stat
sleep 1
read -r cpu_line2 < /proc/stat

set -- $cpu_line1
idle1=$(( $5 )); total1=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 ))
set -- $cpu_line2
idle2=$(( $5 )); total2=$(( $2 + $3 + $4 + $5 + $6 + $7 + $8 ))

idle_delta=$(( idle2 - idle1 ))
total_delta=$(( total2 - total1 ))
if [ "$total_delta" -gt 0 ]; then
  cpu_pct=$(awk -v id="$idle_delta" -v td="$total_delta" 'BEGIN { printf "%.1f", (1 - id/td) * 100 }')
else
  cpu_pct=0
fi

# Memory %
mem_total=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
mem_available=$(awk '/MemAvailable/ {print $2}' /proc/meminfo)
mem_pct=$(awk -v t="$mem_total" -v a="$mem_available" 'BEGIN { printf "%.1f", (1 - a/t) * 100 }')

# Disk % (root filesystem)
disk_pct=$(df / | awk 'NR==2 {gsub("%","",$5); print $5}')

# Uptime in seconds
uptime_seconds=$(awk '{print int($1)}' /proc/uptime)

curl -s -X POST "${HOMELAB_MAP_URL}/api/metrics" \
  -H "Content-Type: application/json" \
  -H "X-Agent-Token: ${AGENT_TOKEN}" \
  -d "{\"cpu_pct\": ${cpu_pct}, \"mem_pct\": ${mem_pct}, \"disk_pct\": ${disk_pct}, \"uptime_seconds\": ${uptime_seconds}}" \
  -o /dev/null -w "homelab-map agent: HTTP %{http_code}\n"
