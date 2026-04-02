# Server Scripts

Production monitoring, cleanup, and backup scripts for `external-compute`.

## Installation

Copy scripts to server and set up crontab:

```bash
# Copy to server
scp scripts/*.sh ubuntu@45.145.22.201:/usr/local/bin/
ssh ubuntu@45.145.22.201 "sudo chmod +x /usr/local/bin/*_agentic.sh"

# Set up crontab
ssh ubuntu@45.145.22.201 "crontab -l"  # verify current crontab

# Add cron jobs (if not already set):
# */5 * * * * /usr/local/bin/monitor_agentic.sh
# 0 3 * * 0   /usr/local/bin/cleanup_agentic.sh
# 0 2 * * *   /usr/local/bin/backup_agentic.sh
```

## Scripts

| Script | Schedule | What it does |
|--------|----------|-------------|
| `monitor_agentic.sh` | Every 5 min | RAM/CPU/Disk check, auto-kills sandboxes if RAM > 85% |
| `cleanup_agentic.sh` | Sunday 03:00 | Docker prune, old temp files, old logs |
| `backup_agentic.sh` | Daily 02:00 | tar.gz backup, keeps last 7 |

## Viewing logs

```bash
journalctl -t agentic-monitor --since "1 hour ago"
journalctl -t agentic-cleanup --since "1 week ago"
journalctl -t agentic-backup --since "1 day ago"
```
