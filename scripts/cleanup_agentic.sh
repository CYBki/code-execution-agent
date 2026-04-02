#!/bin/bash
# Weekly cleanup - runs every Sunday at 03:00 via crontab
# Removes old Docker resources, temp files, and logs

echo "Cleanup started: $(date)" | systemd-cat -t agentic-cleanup

# Docker cleanup
docker system prune -a -f --volumes

# Old sandbox temp files (7+ days)
find /tmp -name "sandbox-*" -mtime +7 -delete 2>/dev/null
find /home/sandbox -name "*.csv" -mtime +7 -delete 2>/dev/null

# Old logs (30+ days)
find /var/log/agentic -name "*.log" -mtime +30 -delete 2>/dev/null

DISK_FREE=$(df -h / | tail -1 | awk '{print $4}')
echo "Cleanup done. Free disk: $DISK_FREE" | systemd-cat -t agentic-cleanup
