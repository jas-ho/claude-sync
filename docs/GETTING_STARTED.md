# Getting Started with claude-sync

This guide walks you through your first sync of Claude.ai projects to your local machine.

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) installed
- Logged into [claude.ai](https://claude.ai) in Edge or Chrome

## Step 1: Find Your Organization UUID

Your org UUID identifies which Claude.ai organization to sync. Choose one of these methods:

### Auto-discovery (easiest)

```bash
./claude_sync.py --list-orgs
```

This lists all organizations you have access to. If you only have one, subsequent syncs will auto-detect it.

### Manual (via browser)

1. Open [claude.ai](https://claude.ai) and log in
2. Open browser DevTools (F12)
3. Go to the **Network** tab
4. Click on any project or refresh the page
5. Look for requests to `https://claude.ai/api/organizations/`
6. Copy the UUID from the URL (format: `f3e5048f-1380-4436-83cf-085832fff594`)

### Environment variable

Save your org UUID to skip typing it each time:

```bash
# Create config file
echo "CLAUDE_ORG_UUID=your-uuid-here" > ~/.claude-sync.env
```

The script also checks for `.claude-sync.env` in the current directory.

## Step 2: Run Your First Sync

```bash
# With explicit org UUID
./claude_sync.py f3e5048f-1380-4436-83cf-085832fff594

# Or if you set up the env file / have only one org
./claude_sync.py
```

Your projects sync to `~/.local/share/claude-sync/` by default.

## Step 3: Verify the Sync

```bash
# Check sync status
./claude_sync.py status

# List synced projects
ls ~/.local/share/claude-sync/
```

Each project becomes a directory containing:
- `CLAUDE.md` - Project instructions
- `meta.json` - Project metadata
- `docs/` - Uploaded documents
- `conversations/` - Chat history as markdown

## Basic Configuration

### Change output directory

```bash
./claude_sync.py -o /path/to/custom/location
```

### Use Chrome instead of Edge

```bash
./claude_sync.py -b chrome
```

### Skip conversations (faster sync)

```bash
./claude_sync.py --skip-conversations
```

### Sync a single project

```bash
./claude_sync.py -p "project-name"
```

### Force full re-sync

```bash
./claude_sync.py --full
```

## Next Steps

- Run `./claude_sync.py --help` for all options
- See the main [README](../README.md) for Claude Code integration, git recovery, and advanced usage
- Set up [automated syncing](../README.md#automated-sync) with launchd/cron
