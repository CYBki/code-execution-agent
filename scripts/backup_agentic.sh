#!/bin/bash
# Daily backup - runs every day at 02:00 via crontab
# Archives project files and config, keeps last 7 backups

BACKUP_DIR=~/backups/agentic
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR

tar -czf $BACKUP_DIR/agentic-$DATE.tar.gz \
  ~/agentic_analyze_d \
  ~/.sandbox.toml \
  2>/dev/null

# Keep only last 7 backups
ls -t $BACKUP_DIR/agentic-*.tar.gz | tail -n +8 | xargs rm -f

SIZE=$(du -h $BACKUP_DIR/agentic-$DATE.tar.gz | awk '{print $1}')
echo "Backup: agentic-$DATE.tar.gz ($SIZE)" | systemd-cat -t agentic-backup
