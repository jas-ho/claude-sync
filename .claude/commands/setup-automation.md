# Setup Automated Sync

Help the user set up scheduled automatic syncing of their Claude.ai projects.

## Overview

This command helps configure periodic automatic syncing using the platform's native scheduler:
- **macOS**: launchd (recommended) or cron
- **Linux**: systemd user timers or cron
- **Windows**: Task Scheduler

## CLI Reference

**IMPORTANT**: The correct CLI flags for claude_sync.py are:
- `--dry-run` - validate config and auth without syncing (use this to test!)
- `--include-standalone` (NOT `--standalone`) - include conversations not in projects
- `-o PATH` or `--output PATH` - custom output directory
- `-b edge|chrome` or `--browser` - browser for cookie extraction
- `--skip-conversations` - skip conversation sync
- `--full` - force full sync, ignore cache
- `--no-git` - disable git auto-commit

Run `uv run --script claude_sync.py sync --help` to see all options.

## Steps

### 1. Gather requirements

Ask the user:
- **Sync frequency**: How often should sync run? (hourly, daily, or custom interval in minutes)
- **Organization UUID**: Check `~/.local/share/claude-sync/index.json` for existing orgs (look in the `orgs` key), or `~/.claude-sync.env`, or ask the user
- **Include standalone conversations?**: Whether to sync conversations not attached to projects (uses `--include-standalone` flag)

### 2. Detect platform and generate config

Based on the platform, generate the appropriate scheduler configuration:

#### macOS (launchd)

Generate a plist file for `~/Library/LaunchAgents/com.claude-sync.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claude-sync</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>uv</string>
        <string>run</string>
        <string>--script</string>
        <string>PATH_TO_SCRIPT/claude_sync.py</string>
        <string>ORG_UUID</string>
        <!-- Add --include-standalone here if user wants standalone conversations -->
    </array>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>HOME/Library/Logs/claude-sync/sync.log</string>
    <key>StandardErrorPath</key>
    <string>HOME/Library/Logs/claude-sync/error.log</string>
    <key>WorkingDirectory</key>
    <string>HOME</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>
</dict>
</plist>
```

For daily sync, use `StartCalendarInterval` instead:
```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>2</integer>
    <key>Minute</key>
    <integer>0</integer>
</dict>
```

**Installation commands:**
```bash
# Create log directory
mkdir -p ~/Library/Logs/claude-sync

# Copy plist (after user confirms content)
cp /path/to/com.claude-sync.plist ~/Library/LaunchAgents/

# Load the service
launchctl load ~/Library/LaunchAgents/com.claude-sync.plist

# Verify it's running
launchctl list | grep claude-sync
```

**Management commands to share:**
```bash
# Check status
launchctl list | grep claude-sync

# View logs
tail -f ~/Library/Logs/claude-sync/sync.log

# Stop service
launchctl unload ~/Library/LaunchAgents/com.claude-sync.plist

# Start service
launchctl load ~/Library/LaunchAgents/com.claude-sync.plist

# Remove completely
launchctl unload ~/Library/LaunchAgents/com.claude-sync.plist
rm ~/Library/LaunchAgents/com.claude-sync.plist
```

#### Linux (systemd user timer)

Generate two files in `~/.config/systemd/user/`:

**claude-sync.service:**
```ini
[Unit]
Description=Sync Claude.ai projects

[Service]
Type=oneshot
ExecStart=/usr/bin/env uv run --script PATH_TO_SCRIPT/claude_sync.py ORG_UUID
WorkingDirectory=%h

[Install]
WantedBy=default.target
```

**claude-sync.timer:**
```ini
[Unit]
Description=Run claude-sync periodically

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

For daily: `OnCalendar=*-*-* 02:00:00`
For custom minutes: `OnUnitActiveSec=30min`

**Installation commands:**
```bash
# Create directory
mkdir -p ~/.config/systemd/user

# Copy files (after user confirms)
# Then enable and start
systemctl --user daemon-reload
systemctl --user enable claude-sync.timer
systemctl --user start claude-sync.timer

# Check status
systemctl --user status claude-sync.timer
systemctl --user list-timers
```

#### Linux/macOS fallback (cron)

For simpler setup or if user prefers cron:

```bash
# Edit crontab
crontab -e

# Add line for hourly sync:
0 * * * * /usr/bin/env uv run --script PATH_TO_SCRIPT/claude_sync.py ORG_UUID >> ~/claude-sync.log 2>&1

# For daily at 2 AM:
0 2 * * * /usr/bin/env uv run --script PATH_TO_SCRIPT/claude_sync.py ORG_UUID >> ~/claude-sync.log 2>&1
```

#### Windows (Task Scheduler)

Provide PowerShell commands or guide through Task Scheduler GUI:

```powershell
# Create a scheduled task for hourly sync
$action = New-ScheduledTaskAction -Execute "uv" -Argument "run --script PATH_TO_SCRIPT\claude_sync.py ORG_UUID"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 1)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable
Register-ScheduledTask -TaskName "ClaudeSync" -Action $action -Trigger $trigger -Settings $settings
```

### 3. Validate the command first

**Before installing automation**, run a dry-run to validate everything works:

```bash
uv run --script /path/to/claude_sync.py ORG_UUID --dry-run --include-standalone
```

The `--dry-run` flag:
- Extracts browser cookies (tests auth)
- Connects to Claude.ai API (tests network/session)
- Lists projects that would be synced
- Shows all configured options
- **Does NOT write any files**

If the dry-run succeeds, the automated sync will work. If it fails, debug before installing automation.

### 4. Confirm and install

1. Show the generated configuration to the user
2. Explain what it does
3. Ask for confirmation before making any changes
4. Create necessary directories (log dirs, config dirs)
5. Write the configuration file
6. Provide the commands to activate the scheduler
7. Verify it's working

### 5. Provide ongoing management info

After setup, remind user:
- Where logs are stored
- How to check if sync is running
- How to temporarily disable
- How to uninstall completely

## Guidelines

- **Always ask before writing files** - show content first, get confirmation
- **Detect the script path** - find where claude_sync.py is located
- **Validate org UUID** - ensure it's a valid UUID format
- **Create log directories** - ensure log paths exist before installing
- **Test the sync first** - recommend running sync manually once before automating
- **Handle existing setups** - check if automation is already configured and offer to update/remove

## Expected User Experience

User runs `/setup-automation` and:
1. Gets asked about sync frequency preference
2. Sees the generated configuration with explanation
3. Confirms before any files are written
4. Gets clear instructions for managing the automation
5. Knows where to find logs and how to troubleshoot
