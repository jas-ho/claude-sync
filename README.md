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

The easiest method is auto-discovery:

```bash
./claude_sync.py --list-orgs
```

This lists all organizations you have access to. Save your UUID to `~/.claude-sync.env` to avoid typing it each time:

```bash
echo "CLAUDE_ORG_UUID=your-uuid-here" > ~/.claude-sync.env
```

For alternative methods (browser DevTools) and troubleshooting, see [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md).

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

### Common Options

| Flag | Description |
|------|-------------|
| `-o, --output` | Output directory (default: `~/.local/share/claude-sync`) |
| `-p, --project` | Sync only matching project (UUID or name substring) |
| `--skip-conversations` | Skip syncing conversations (faster) |
| `--include-standalone` | Include standalone conversations (not in projects) |
| `--full` | Force full sync, ignore cache |
| `--no-git` | Disable automatic git commits |
| `-b, --browser` | Browser to extract cookies from (`edge` or `chrome`) |
| `-v, --verbose` | Enable verbose output |

For all options, see [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

### Incremental Sync

By default, **claude-sync** only downloads changed content:

- Detects updated projects via `updated_at` timestamps
- Compares document content hashes
- Checks conversation update times

Use `--full` to force re-download everything.

### Standalone Conversations

By default, only conversations within projects are synced. To include standalone conversations (not attached to any project):

```bash
./claude_sync.py <org-uuid> --include-standalone
```

Standalone conversations are saved to the `_standalone/` directory.

## Output Structure

```
~/.local/share/claude-sync/
├── .git/                            # Git repository (auto-initialized)
├── index.json                       # Project manifest
├── _standalone/                     # Standalone conversations (--include-standalone)
└── project-name-abc12345/           # One directory per project
    ├── CLAUDE.md                    # Project instructions
    ├── meta.json                    # Project metadata
    ├── docs/                        # Project documents
    └── conversations/               # Conversation history as markdown
```

Each project contains **CLAUDE.md** (instructions with YAML frontmatter), **meta.json** (metadata), and **conversations/*.md** (chat history).

## Claude Code Integration

Reference synced projects in your `CLAUDE.md`:

```markdown
## Style Guide
@~/.local/share/claude-sync/style-guide-abc12345/CLAUDE.md

## Requirements
See: @~/.local/share/claude-sync/my-project-abc12345/docs/requirements.md
```

Search conversations: `grep -r "keyword" ~/.local/share/claude-sync/*/conversations/`

## Git Recovery

The output directory is a git repository with commits for each sync. Recover overwrites with:

```bash
cd ~/.local/share/claude-sync
git diff HEAD~1 -- project-name/CLAUDE.md    # View changes
git checkout HEAD~1 -- project-name/CLAUDE.md # Restore previous
git log --oneline                             # View history
```

Don't edit synced files directly - they'll be overwritten. Use `--no-git` for manual control.

## Privacy & Security

- **Cookie extraction:** Reads browser cookies from local disk (read-only)
- **No credentials stored:** Session cookies are used per-run, not saved
- **Local storage only:** All data stays on your machine
- **Read-only API:** Tool only reads from Claude.ai, never writes
- **Sensitive data redaction:** Logs automatically redact tokens and keys

**Never commit `.claude-sync.env` with your org UUID to public repositories.**

## Troubleshooting

Common issues include cookie extraction problems, session expiry, and rate limiting. Most can be resolved by:

1. Closing your browser and retrying
2. Re-authenticating at claude.ai
3. Waiting a few minutes for rate limits

For detailed solutions, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Configuration

Environment variables and all command-line flags are documented in [docs/CONFIGURATION.md](docs/CONFIGURATION.md).

## Advanced Usage

For automated sync (launchd, cron, systemd), syncing multiple organizations, backup strategies, and selective sync patterns, see [docs/ADVANCED_USAGE.md](docs/ADVANCED_USAGE.md).

## Documentation

- [Getting Started](docs/GETTING_STARTED.md) - Finding your org UUID, first sync
- [Configuration](docs/CONFIGURATION.md) - All flags and environment variables
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common errors and solutions
- [Advanced Usage](docs/ADVANCED_USAGE.md) - Automation, backups, selective sync
- [API Contract](docs/API_CONTRACT.md) - Claude.ai API response structures
- [Implementation Notes](docs/IMPLEMENTATION_NOTES.md) - Edge cases and findings

## Contributing

Contributions welcome! This is a single-file script, so changes are straightforward:

1. Edit `claude_sync.py`
2. Test locally
3. Submit PR

Use [bd (beads)](https://github.com/steveyegge/beads) for issue tracking (see `AGENTS.md`).

## License

MIT
