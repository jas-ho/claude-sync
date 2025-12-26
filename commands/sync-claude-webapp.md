---
description: Sync Claude.ai web conversations to local disk (~/.local/share/claude-sync/)
---

Sync Claude.ai web app projects and conversations to local disk.

## What This Does

- Extracts session cookies from browser (Edge)
- Fetches projects and conversations from claude.ai API
- Saves to `~/.local/share/claude-sync/` with incremental updates
- Commits changes to the local git repo

## Run the Sync

Execute the sync script:

```bash
~/.claude/user-automations/run-claude-sync.sh
```

This runs the same script as the daily 2 AM automation.

## After Sync

Show summary of what was synced:

```bash
cd ~/.local/share/claude-sync
git log --oneline -5
```

## Troubleshooting

If sync fails with "Resource not found" (404), your browser session may have switched accounts. Find the correct org UUID:

```bash
cd ~/Code/claude-sync && uv run ./claude_sync.py --list-orgs
```

Then update the org UUID in `~/.claude/user-automations/run-claude-sync.sh` and `~/Library/LaunchAgents/com.claude-sync.plist`.

## Related Files

- **Automation**: `~/Library/LaunchAgents/com.claude-sync.plist` (daily at 2 AM)
- **Wrapper**: `~/.claude/user-automations/run-claude-sync.sh`
- **Script**: `~/Code/claude-sync/claude_sync.py`
- **Output**: `~/.local/share/claude-sync/`
- **Logs**: `~/Library/Logs/automations/claude-sync.log`
