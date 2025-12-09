# claude-sync

Sync Claude.ai web app projects to local filesystem for use with Claude Code.

## Overview

**claude-sync** downloads your Claude.ai projects, documents, and conversation history to a local directory structure. This enables:

- **Local access** to project documentation and style guides
- **Search** through conversation history
- **Integration** with Claude Code via project instructions
- **Version control** with automatic git commits

Built as a single-file UV script with inline dependencies - no installation required.

## Quick Start

```bash
# 1. Download the script
curl -O https://raw.githubusercontent.com/jas-ho/claude-sync/main/claude_sync.py
chmod +x claude_sync.py

# 2. Find your org UUID (see below)

# 3. Run sync
./claude_sync.py <your-org-uuid>
```

Your projects will be synced to `~/.local/share/claude-sync/`.

## Installation

No installation needed! Just download `claude_sync.py` and make it executable:

```bash
chmod +x claude_sync.py
```

**Requirements:**

- Python 3.12+
- `uv` (the script uses inline dependency specification)
- Logged into claude.ai in your browser (Edge or Chrome)

Dependencies (`curl_cffi`, `tqdm`, `browser-cookie3`) are automatically managed by `uv`.

## Finding Your Org UUID

Your organization UUID is needed to sync your projects. Two methods:

### Method 1: Auto-discovery (easiest)

```bash
./claude_sync.py --list-orgs
```

This will list all organizations you have access to.

### Method 2: Manual (via browser)

1. Open [claude.ai](https://claude.ai) and log in
1. Open browser DevTools (F12)
1. Go to the **Network** tab
1. Click on any project or refresh the page
1. Look for requests to `https://claude.ai/api/organizations/`
1. Copy the UUID from the URL (format: `f3e5048f-1380-4436-83cf-085832fff594`)

### Method 3: Environment variable

Save your org UUID to avoid typing it each time:

```bash
# Create config file
echo "CLAUDE_ORG_UUID=your-uuid-here" > ~/.claude-sync.env
```

Then just run `./claude_sync.py` without arguments.

## Usage

### Basic Sync

```bash
# Sync all projects
./claude_sync.py <org-uuid>

# Auto-discover org (if you only have one)
./claude_sync.py
```

### Check Sync Status

```bash
# Show local status (no auth required)
./claude_sync.py status

# Check for remote changes
./claude_sync.py status --remote

# Thorough check including document changes (slow)
./claude_sync.py status --remote --check-docs
```

### Options

```bash
# Custom output directory
./claude_sync.py <org-uuid> -o /path/to/output

# Full sync (ignore cache, re-download everything)
./claude_sync.py <org-uuid> --full

# Skip conversations (faster sync, only docs)
./claude_sync.py <org-uuid> --skip-conversations

# Include standalone conversations (not in projects)
./claude_sync.py <org-uuid> --include-standalone

# Sync only one project (by name or UUID)
./claude_sync.py <org-uuid> -p "my-project"
./claude_sync.py <org-uuid> -p abc12345

# Use Chrome instead of Edge
./claude_sync.py <org-uuid> -b chrome

# Verbose output (debugging)
./claude_sync.py <org-uuid> -v

# Disable git auto-commit
./claude_sync.py <org-uuid> --no-git

# List available organizations
./claude_sync.py --list-orgs
```

### Incremental Sync

By default, **claude-sync** only downloads changed content:

- Detects updated projects via `updated_at` timestamps
- Compares document content hashes
- Checks conversation update times
- Skips unchanged data

Use `--full` to force re-download everything.

### Standalone Conversations

By default, **claude-sync** only syncs conversations within projects. You can also sync standalone conversations (conversations not attached to any project) using the `--include-standalone` flag:

```bash
./claude_sync.py <org-uuid> --include-standalone
```

Standalone conversations are saved to the `_standalone/` directory at the root of your output directory.

## Output Structure

```
~/.local/share/claude-sync/          # Default output directory
├── .git/                            # Git repository (auto-initialized)
├── .sync-state.json                 # Internal sync state (timestamps, hashes)
├── index.json                       # Project manifest
├── .backup/                         # Timestamped backups of changed files
├── _standalone/                     # Standalone conversations (not in projects)
│   ├── index.json                   # Standalone conversation manifest
│   └── <conversation-name>.md       # Individual conversations (named by title)
└── project-name-abc12345/           # One directory per project
    ├── CLAUDE.md                    # Project instructions (from prompt_template)
    ├── meta.json                    # Project metadata
    ├── docs/                        # Project documents
    │   ├── style-guide.md
    │   └── requirements.md
    └── conversations/               # Conversation history
        ├── index.json               # Conversation manifest
        └── <conversation-name>.md   # Individual conversations (named by title)
```

### File Formats

**CLAUDE.md** - Project instructions with frontmatter:

```markdown
---
synced_at: 2025-12-07T10:30:00+00:00
source: claude.ai/project/abc-123
---

Your project instructions here...
```

**meta.json** - Project metadata:

```json
{
  "uuid": "abc-123",
  "name": "My Project",
  "description": "...",
  "created_at": "2025-01-01T00:00:00Z",
  "updated_at": "2025-12-07T10:30:00Z",
  "synced_at": "2025-12-07T10:30:00+00:00"
}
```

**conversations/\*.md** - Conversation history in markdown:

```markdown
---
conversation_id: xyz-789
name: My Conversation
created_at: 2025-12-01T00:00:00Z
updated_at: 2025-12-07T10:00:00Z
message_count: 42
synced_at: 2025-12-07T10:30:00+00:00
---

# My Conversation

## **Human** (2025-12-01 10:00)

Hello!

---

## **Claude** (2025-12-01 10:01)

Hi there! How can I help?

---
```

## Claude Code Integration

Use synced projects with Claude Code by referencing them in your project's `CLAUDE.md`:

### Option 1: Import project instructions

```markdown
<!-- In your project's CLAUDE.md -->

## Style Guide

@~/.local/share/claude-sync/style-guide-abc12345/CLAUDE.md
```

### Option 2: Reference specific docs

```markdown
## Requirements

See synced requirements: @~/.local/share/claude-sync/my-project-abc12345/docs/requirements.md
```

### Option 3: Search conversations

Use `grep` or your editor's search to find discussions:

```bash
grep -r "authentication" ~/.local/share/claude-sync/*/conversations/
```

## Git Recovery Workflow

**Important:** The output directory is automatically initialized as a git repository. Every sync creates a commit, allowing you to recover from accidental overwrites.

### View what changed in last sync

```bash
cd ~/.local/share/claude-sync

# See changes to a specific file
git diff HEAD~1 -- project-name-abc12345/CLAUDE.md

# See all changes from last sync
git show HEAD
```

### Restore previous version

```bash
# Restore a single file
git checkout HEAD~1 -- project-name-abc12345/CLAUDE.md

# Restore entire project directory
git checkout HEAD~1 -- project-name-abc12345/

# Go back 3 syncs
git checkout HEAD~3 -- project-name-abc12345/CLAUDE.md
```

### View sync history

```bash
# List recent syncs
git log --oneline

# See full diff from 2 syncs ago
git diff HEAD~2

# See when a file was changed
git log -- project-name-abc12345/docs/style-guide.md
```

### Best Practices

- **Don't edit synced files directly** - They'll be overwritten on next sync
- **Use git to recover** - Every sync creates a checkpoint
- **For local modifications:**
  - Create separate files alongside synced content
  - Or use git branches: `git checkout -b local-edits`
  - Or disable auto-commit: `--no-git` and manage git manually

### Disable auto-commit

If you want full control over git:

```bash
./claude_sync.py <org-uuid> --no-git
```

Then manage commits yourself:

```bash
cd ~/.local/share/claude-sync
git add -A
git commit -m "Manual sync"
```

## Configuration

### Command-line flags

#### Sync command

| Flag | Default | Description |
|------|---------|-------------|
| `<org-uuid>` | Auto-discover | Organization UUID (optional if only one org) |
| `-o, --output` | `~/.local/share/claude-sync` | Output directory |
| `-b, --browser` | `edge` | Browser to extract cookies from (`edge` or `chrome`) |
| `--skip-conversations` | `false` | Skip syncing conversations (faster) |
| `--include-standalone` | `false` | Include standalone conversations (not in projects) |
| `-p, --project` | All projects | Sync only matching project (UUID or name substring) |
| `--full` | `false` | Force full sync, ignore cache |
| `--no-git` | `false` | Disable automatic git commits |
| `-v, --verbose` | `false` | Enable verbose output |
| `--min-disk-mb` | `100` | Minimum free disk space in MB |
| `--list-orgs` | N/A | List available organizations and exit |

#### Status command

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `~/.local/share/claude-sync` | Output directory |
| `--remote` | `false` | Check for changes on claude.ai (requires authentication) |
| `--check-docs` | `false` | Check for document changes (requires --remote, may be slow) |
| `-b, --browser` | `edge` | Browser to extract cookies from (`edge` or `chrome`) |

### Environment variables

Create `~/.claude-sync.env`:

```bash
CLAUDE_ORG_UUID=f3e5048f-1380-4436-83cf-085832fff594
```

Or `.claude-sync.env` in your current directory.

## Troubleshooting

### Cookie extraction issues

**Error:** `Permission denied accessing edge cookies`

**Solution:**

1. Close your browser completely
1. On macOS: Grant Terminal/IDE access in **System Preferences > Security & Privacy > Privacy > Full Disk Access**
1. Retry

**Error:** `Browser cookie database is locked`

**Solution:** Close your browser and retry.

**Error:** `Missing required cookie(s): sessionKey`

**Solution:**

1. Log into [claude.ai](https://claude.ai) in your browser
1. Refresh the page
1. Retry sync

### Session expiry

**Error:** `Session expired or invalid`

**Solution:**

1. Open claude.ai in your browser
1. Log out and log back in
1. Retry sync

The session cookies expire periodically. Just re-authenticate in your browser.

### Rate limiting

**Error:** `Rate limited by Claude.ai`

**Solution:** Wait a few minutes and try again. The sync tool includes automatic delays between requests, but syncing many large projects may trigger rate limits.

### Cloudflare blocking

**Error:** `API returned HTML instead of JSON` or `Cloudflare blocked the request`

**Solution:**

1. Wait a few minutes
1. Verify claude.ai is accessible in your browser
1. Retry

This usually resolves itself. The tool uses browser impersonation to minimize blocking.

### Concurrent sync error

**Error:** `Another sync is running (PID: 12345)`

**Solution:**

- Wait for the other sync to complete, or
- If the PID is stale (process died), delete `~/.local/share/claude-sync/.claude-sync.lock`

### Disk space

**Error:** `Insufficient disk space`

**Solution:**

- Free up space, or
- Use a different output directory: `-o /path/with/more/space`

### Large files skipped

**Warning:** `Skipping doc '...': 12.5MB exceeds 10MB limit`

**Explanation:** Documents larger than 10MB are automatically skipped to prevent memory exhaustion. This is a safety limit.

**Workaround:** Download large files manually from claude.ai web interface.

### Conversation message limits

**Warning:** `Skipping conversation '...': 15000 messages exceeds 10000 limit`

**Explanation:** Conversations with more than 10,000 messages are skipped to prevent excessive API usage and memory consumption.

### Common errors

| Error | Cause | Solution |
|-------|-------|----------|
| `FileNotFoundError: Resource not found` | Project/doc deleted remotely during sync | Normal - item was deleted, sync continues |
| `Slug collision` | Two projects generated same directory name | Manually rename one project directory |
| `Invalid JSON in API response` | Network corruption or API change | Retry; report if persistent |
| `Git not found in PATH` | Git not installed | Install git, or use `--no-git` |

## Advanced Usage

### Automated sync

#### Claude Code users

Use the `/setup-automation` slash command in Claude Code for an interactive setup that supports:
- macOS (launchd)
- Linux (systemd user timers or cron)
- Windows (Task Scheduler)

#### Manual setup (cron)

```bash
# Add to crontab: sync every hour
0 * * * * /path/to/claude_sync.py f3e5048f-1380-4436-83cf-085832fff594 >> ~/claude-sync.log 2>&1
```

### Sync multiple organizations

```bash
# Use different output directories
./claude_sync.py org1-uuid -o ~/.local/share/claude-sync/org1
./claude_sync.py org2-uuid -o ~/.local/share/claude-sync/org2
```

### Backup synced data

The output directory is a git repository, so you can:

```bash
# Push to remote for backup
cd ~/.local/share/claude-sync
git remote add origin git@github.com:yourusername/claude-projects.git
git push -u origin main

# Or create archive
tar czf claude-sync-backup.tar.gz ~/.local/share/claude-sync
```

### Selective sync

```bash
# Sync only documentation (no conversations)
./claude_sync.py <org-uuid> --skip-conversations

# Sync single project
./claude_sync.py <org-uuid> -p "production-docs"

# Full sync of one project
./claude_sync.py <org-uuid> -p "my-project" --full
```

## Privacy & Security

- **Cookie extraction:** Reads browser cookies from local disk (read-only)
- **No credentials stored:** Session cookies are used per-run, not saved
- **Local storage only:** All data stays on your machine
- **Read-only API:** Tool only reads from Claude.ai, never writes
- **Sensitive data redaction:** Logs automatically redact tokens and keys

**Never commit `.claude-sync.env` with your org UUID to public repositories.**

## License

MIT

## Contributing

Contributions welcome! This is a single-file script, so changes are straightforward:

1. Edit `claude_sync.py`
1. Test locally
1. Submit PR

Use [bd (beads)](https://github.com/steveyegge/beads) for issue tracking (see `AGENTS.md`).

## Support

For issues or questions:

- Check **Troubleshooting** section above
- Review `docs/RESEARCH.md` for API details
- Open an issue with `bd` or GitHub Issues
