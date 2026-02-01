# Advanced Usage

This guide covers advanced configuration and usage patterns for claude-sync.

## Automated Sync Setup

### Claude Code Users (Recommended)

If you're using Claude Code, the easiest way to set up automation is with the built-in slash command:

```
/setup-automation
```

This provides an interactive setup that handles platform-specific configuration for macOS (launchd), Linux (systemd/cron), and Windows (Task Scheduler).

### macOS (launchd)

Create a plist file at `~/Library/LaunchAgents/com.claude-sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/.local/bin/uv</string>
        <string>run</string>
        <string>/path/to/claude_sync.py</string>
        <string>YOUR-ORG-UUID</string>
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/automations/claude-sync.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/automations/claude-sync.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/Users/YOUR_USERNAME/.local/bin</string>
    </dict>
</dict>
</plist>
```

Load the agent:

```bash
# Create log directory
mkdir -p ~/Library/Logs/automations

# Load the agent
launchctl load ~/Library/LaunchAgents/com.claude-sync.plist

# Check status
launchctl list | grep claude-sync

# View logs
tail -f ~/Library/Logs/automations/claude-sync.log

# Unload if needed
launchctl unload ~/Library/LaunchAgents/com.claude-sync.plist
```

**Important notes:**

- Use absolute paths for `uv` and the script
- Include `$HOME/.local/bin` in PATH for uv access
- Browser must remain logged into claude.ai for cookie extraction

### Linux (systemd user timer)

Create `~/.config/systemd/user/claude-sync.service`:

```ini
[Unit]
Description=Sync Claude.ai projects
After=network-online.target

[Service]
Type=oneshot
ExecStart=/home/YOUR_USERNAME/.local/bin/uv run /path/to/claude_sync.py YOUR-ORG-UUID
Environment="PATH=/home/YOUR_USERNAME/.local/bin:/usr/local/bin:/usr/bin:/bin"
StandardOutput=append:/home/YOUR_USERNAME/.local/share/claude-sync/sync.log
StandardError=append:/home/YOUR_USERNAME/.local/share/claude-sync/sync.log
```

Create `~/.config/systemd/user/claude-sync.timer`:

```ini
[Unit]
Description=Run claude-sync hourly

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable claude-sync.timer
systemctl --user start claude-sync.timer

# Check status
systemctl --user status claude-sync.timer
systemctl --user list-timers

# View logs
journalctl --user -u claude-sync.service -f
```

### Linux/macOS (cron)

Add to your crontab with `crontab -e`:

```bash
# Sync every hour
0 * * * * /path/to/uv run /path/to/claude_sync.py YOUR-ORG-UUID >> ~/.local/share/claude-sync/sync.log 2>&1

# Sync every 4 hours
0 */4 * * * /path/to/uv run /path/to/claude_sync.py YOUR-ORG-UUID >> ~/.local/share/claude-sync/sync.log 2>&1

# Sync daily at 6 AM
0 6 * * * /path/to/uv run /path/to/claude_sync.py YOUR-ORG-UUID >> ~/.local/share/claude-sync/sync.log 2>&1
```

**Cron tips:**

- Use absolute paths (cron has minimal PATH)
- Redirect both stdout and stderr to a log file
- Test your cron command manually first

### Monitoring Automated Syncs

For unattended automation, consider using a monitoring service like [healthchecks.io](https://healthchecks.io):

```bash
# Wrapper script with healthchecks.io ping
#!/bin/bash
HEALTHCHECK_URL="https://hc-ping.com/YOUR-CHECK-UUID"

# Ping start
curl -fsS -m 10 --retry 5 "${HEALTHCHECK_URL}/start" > /dev/null

# Run sync
/path/to/uv run /path/to/claude_sync.py YOUR-ORG-UUID

# Capture exit code
EXIT_CODE=$?

# Ping success or failure
if [ $EXIT_CODE -eq 0 ]; then
    curl -fsS -m 10 --retry 5 "${HEALTHCHECK_URL}" > /dev/null
else
    curl -fsS -m 10 --retry 5 "${HEALTHCHECK_URL}/fail" > /dev/null
fi

exit $EXIT_CODE
```

## Syncing Multiple Organizations

If you have access to multiple Claude.ai organizations (e.g., personal and work), sync them to separate directories:

```bash
# Sync personal org
./claude_sync.py personal-org-uuid -o ~/.local/share/claude-sync/personal

# Sync work org
./claude_sync.py work-org-uuid -o ~/.local/share/claude-sync/work
```

### Automation for Multiple Orgs

Create a wrapper script `~/bin/claude-sync-all`:

```bash
#!/bin/bash
set -e

SYNC_SCRIPT="/path/to/claude_sync.py"
LOG_DIR="$HOME/Library/Logs/automations"

echo "$(date): Starting multi-org sync" >> "$LOG_DIR/claude-sync.log"

# Sync personal
echo "Syncing personal org..." >> "$LOG_DIR/claude-sync.log"
uv run "$SYNC_SCRIPT" PERSONAL-ORG-UUID -o ~/.local/share/claude-sync/personal >> "$LOG_DIR/claude-sync.log" 2>&1

# Sync work
echo "Syncing work org..." >> "$LOG_DIR/claude-sync.log"
uv run "$SYNC_SCRIPT" WORK-ORG-UUID -o ~/.local/share/claude-sync/work >> "$LOG_DIR/claude-sync.log" 2>&1

echo "$(date): Multi-org sync complete" >> "$LOG_DIR/claude-sync.log"
```

Then point your launchd/systemd/cron job at this wrapper script.

### Environment File for Multiple Orgs

You can also use multiple environment files:

```bash
# ~/.claude-sync-personal.env
CLAUDE_ORG_UUID=personal-org-uuid

# ~/.claude-sync-work.env
CLAUDE_ORG_UUID=work-org-uuid
```

Reference them explicitly in your automation scripts.

## Backup Strategies

### Git Remote Backup

Since the output directory is a git repository, push to a remote for backup:

```bash
cd ~/.local/share/claude-sync

# Add remote (first time only)
git remote add origin git@github.com:yourusername/claude-projects-backup.git

# Push (after each sync, or add to automation)
git push origin main
```

**Security note:** If your synced content contains sensitive information, use a private repository.

### Automated Git Push

Add to your sync wrapper script:

```bash
#!/bin/bash
SYNC_DIR="$HOME/.local/share/claude-sync"
SYNC_SCRIPT="/path/to/claude_sync.py"

# Run sync
uv run "$SYNC_SCRIPT" YOUR-ORG-UUID

# Push to remote backup
cd "$SYNC_DIR"
if git remote get-url origin > /dev/null 2>&1; then
    git push origin main --quiet
fi
```

### Restic Backup

If you use restic for backups, include the sync directory:

```bash
# Add to your restic backup command
restic backup ~/.local/share/claude-sync
```

### Archive Backup

Create periodic archives:

```bash
# Weekly archive
tar czf ~/Backups/claude-sync-$(date +%Y%m%d).tar.gz ~/.local/share/claude-sync

# Exclude git history for smaller archives
tar czf ~/Backups/claude-sync-$(date +%Y%m%d).tar.gz \
    --exclude='.git' \
    ~/.local/share/claude-sync
```

### Backup Rotation Script

```bash
#!/bin/bash
BACKUP_DIR="$HOME/Backups/claude-sync"
SYNC_DIR="$HOME/.local/share/claude-sync"
KEEP_DAYS=30

mkdir -p "$BACKUP_DIR"

# Create dated backup
tar czf "$BACKUP_DIR/claude-sync-$(date +%Y%m%d).tar.gz" "$SYNC_DIR"

# Remove backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "claude-sync-*.tar.gz" -mtime +$KEEP_DAYS -delete
```

## Selective Sync Patterns

### Documentation Only (Fast)

Skip conversations for quick syncs of just project instructions and documents:

```bash
./claude_sync.py YOUR-ORG-UUID --skip-conversations
```

This is useful for:
- Initial exploration of projects
- CI/CD pipelines that only need docs
- Reducing sync time on large orgs

### Single Project Sync

Sync only a specific project by name or UUID:

```bash
# By name (substring match)
./claude_sync.py YOUR-ORG-UUID -p "production-docs"
./claude_sync.py YOUR-ORG-UUID -p "style-guide"

# By UUID (exact match)
./claude_sync.py YOUR-ORG-UUID -p abc12345-6789-0abc-def0-123456789abc
```

### Full Refresh of One Project

Force re-download of a specific project (useful after corruption):

```bash
./claude_sync.py YOUR-ORG-UUID -p "my-project" --full
```

### Include Standalone Conversations

Sync conversations that aren't attached to any project:

```bash
./claude_sync.py YOUR-ORG-UUID --include-standalone
```

Standalone conversations appear in `_standalone/` at the output root.

### Combined Patterns

```bash
# Fast sync: specific project, docs only
./claude_sync.py YOUR-ORG-UUID -p "api-docs" --skip-conversations

# Complete sync: everything including standalone
./claude_sync.py YOUR-ORG-UUID --include-standalone

# Refresh: full sync of important project
./claude_sync.py YOUR-ORG-UUID -p "critical-project" --full

# Minimal sync: just project instructions
./claude_sync.py YOUR-ORG-UUID --skip-conversations
```

## Troubleshooting Automation

### Common Issues

**Session expiry in automation:**

Browser sessions expire periodically. If your automated sync starts failing:

1. Log into claude.ai in your browser
2. Refresh the page to renew cookies
3. The next automated sync should work

**Account mismatch (404 errors):**

If you switch Claude accounts in your browser, the org UUID may no longer match. Run:

```bash
./claude_sync.py --list-orgs
```

To see which org your current session has access to.

**Browser not accessible:**

Automation jobs may not have access to browser cookies if the browser is in a different security context. Ensure:

- The automation runs as your user (not root)
- Browser data is accessible from the automation context
- On macOS: Full Disk Access may be needed for Terminal/automation tool

### Debug Mode

For troubleshooting automation issues:

```bash
./claude_sync.py YOUR-ORG-UUID -v >> ~/claude-sync-debug.log 2>&1
```

The `-v` flag enables verbose output showing API calls and timing.

### Dry Run Validation

Test your config without writing files:

```bash
./claude_sync.py YOUR-ORG-UUID --dry-run
```

This validates authentication and API access without making any changes.
