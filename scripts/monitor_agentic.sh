#!/bin/bash
# Agentic resource monitoring - runs every 5 minutes via crontab
# Checks RAM, CPU, Disk and takes action if thresholds exceeded

LOG_TAG="agentic-monitor"

# RAM usage (threshold: 85%)
RAM_USAGE=$(free | grep Mem | awk '{print ($3/$2) * 100.0}')
if (( $(echo "$RAM_USAGE > 85" | bc -l) )); then
  echo "ALERT: RAM usage ${RAM_USAGE}%" | systemd-cat -t $LOG_TAG -p err

  # Stop 2 oldest sandboxes to free memory
  docker ps --filter "label=opensandbox" --format "{{.CreatedAt}}\t{{.ID}}" | \
    sort | head -n 2 | awk '{print $NF}' | xargs -r docker stop

  echo "2 sandboxes stopped (RAM recovery)" | systemd-cat -t $LOG_TAG -p warning
fi

# CPU load (16 vCPU, threshold 80% = 12.8)
CPU_LOAD=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
if (( $(echo "$CPU_LOAD > 12.8" | bc -l) )); then
  echo "WARNING: CPU load $CPU_LOAD (threshold: 12.8)" | systemd-cat -t $LOG_TAG -p warning
fi

# Disk usage (threshold: 90%)
DISK_USAGE=$(df -h / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 90 ]; then
  echo "ALERT: Disk usage ${DISK_USAGE}%" | systemd-cat -t $LOG_TAG -p err
  docker system prune -f --volumes
fi

# Active sandbox count
ACTIVE=$(docker ps --filter "label=opensandbox" --quiet | wc -l)
echo "RAM: ${RAM_USAGE}% | CPU: $CPU_LOAD | Disk: ${DISK_USAGE}% | Sandboxes: $ACTIVE" | \
  systemd-cat -t $LOG_TAG -p info
