# Configuration Reference

Complete reference for all claude-sync configuration options.

## Command-Line Flags

### Sync Command

The main sync command downloads projects, documents, and conversations from Claude.ai.

```bash
./claude_sync.py [ORG_UUID] [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `<org-uuid>` | Auto-discover | Organization UUID. Optional if only one org exists or `CLAUDE_ORG_UUID` is set. |
| `-o, --output` | `~/.local/share/claude-sync` | Output directory for synced content |
| `-b, --browser` | `edge` | Browser to extract cookies from (`edge` or `chrome`) |
| `--skip-conversations` | `false` | Skip syncing conversations (faster, docs only) |
| `--include-standalone` | `false` | Include standalone conversations (not in any project) |
| `-p, --project` | All projects | Sync only matching project (UUID or name substring) |
| `--full` | `false` | Force full sync, ignore cache and re-download everything |
| `--no-git` | `false` | Disable automatic git commits after sync |
| `-v, --verbose` | `false` | Enable verbose output for debugging |
| `--min-disk-mb` | `100` | Minimum required free disk space in MB before sync |
| `--list-orgs` | N/A | List available organizations and exit (no sync) |
| `--dry-run` | `false` | Validate configuration without writing files |

#### Examples

```bash
# Basic sync with auto-discovered org
./claude_sync.py

# Sync specific org to custom directory
./claude_sync.py f3e5048f-1380-4436-83cf-085832fff594 -o ~/my-claude-data

# Fast sync - skip conversations
./claude_sync.py --skip-conversations

# Force full re-download
./claude_sync.py --full

# Sync single project by name
./claude_sync.py -p "my-project-name"

# Sync single project by UUID
./claude_sync.py -p abc12345-6789-0123-4567-890abcdef012

# Use Chrome instead of Edge for cookies
./claude_sync.py -b chrome

# Include standalone conversations
./claude_sync.py --include-standalone

# Verbose output for debugging
./claude_sync.py -v

# Disable git auto-commit
./claude_sync.py --no-git

# Validate config without syncing
./claude_sync.py --dry-run
```

### Status Command

Check sync health and detect remote changes without running a full sync.

```bash
./claude_sync.py status [OPTIONS]
```

| Flag | Default | Description |
|------|---------|-------------|
| `-o, --output` | `~/.local/share/claude-sync` | Output directory to check |
| `--remote` | `false` | Check for changes on claude.ai (requires authentication) |
| `--check-docs` | `false` | Check for document changes (requires `--remote`, may be slow) |
| `-b, --browser` | `edge` | Browser to extract cookies from (`edge` or `chrome`) |

#### Local Status (No Auth Required)

Shows information from local sync state only:

- Last sync time and age
- Project, document, conversation counts
- Recently active projects
- Integrity check (directories match manifest)

```bash
./claude_sync.py status
./claude_sync.py status -o ~/custom-sync-dir
```

#### Remote Status (Requires Auth)

Compares local state with Claude.ai to detect:

- New projects on claude.ai
- Modified project instructions
- New/modified conversations
- Deleted projects

```bash
./claude_sync.py status --remote
./claude_sync.py status --remote -b chrome
```

#### Document Checking

Detects new, modified, or deleted documents. Slower because it fetches all document metadata.

```bash
./claude_sync.py status --remote --check-docs
```

## Environment Variables

### Config File Locations

Environment variables are loaded from config files in this order (later files override earlier):

1. `~/.claude-sync.env` (user home directory)
2. `.claude-sync.env` (current working directory)

### Supported Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `CLAUDE_ORG_UUID` | Default organization UUID | `f3e5048f-1380-4436-83cf-085832fff594` |

### Config File Format

Plain text file with `KEY=value` format:

```bash
# ~/.claude-sync.env
CLAUDE_ORG_UUID=f3e5048f-1380-4436-83cf-085832fff594
```

**Security Note:** Never commit `.claude-sync.env` to public repositories.

## File Locations

### Output Directory Structure

Default: `~/.local/share/claude-sync/`

```
<output-dir>/
├── .git/                            # Git repository (auto-initialized)
├── .sync-state.json                 # Internal sync state (timestamps, hashes)
├── .claude-sync.lock                # Lock file preventing concurrent syncs
├── .backup/                         # Timestamped backups of changed files
├── index.json                       # Project manifest with sync metadata
├── _standalone/                     # Standalone conversations (if --include-standalone)
│   ├── index.json                   # Standalone conversation manifest
│   └── <conversation-name>.md       # Individual conversations
└── <project-slug>/                  # One directory per project
    ├── CLAUDE.md                    # Project instructions
    ├── meta.json                    # Project metadata
    ├── docs/                        # Project documents
    └── conversations/               # Conversation history
        ├── index.json               # Conversation manifest
        └── <conversation-name>.md   # Individual conversations
```

### Lock File

Location: `<output-dir>/.claude-sync.lock`

Prevents concurrent sync operations. Contains PID of running sync process.

If a sync crashes, the lock file may become stale. Delete it manually to allow new syncs:

```bash
rm ~/.local/share/claude-sync/.claude-sync.lock
```

### Sync State

Location: `<output-dir>/.sync-state.json`

Internal file tracking:

- Last sync timestamp
- Content hashes for incremental sync
- Project/document/conversation metadata

Do not edit manually. Use `--full` to force a fresh sync if state becomes corrupted.

## Default Values Summary

| Setting | Default Value |
|---------|---------------|
| Output directory | `~/.local/share/claude-sync` |
| Browser | `edge` |
| Minimum disk space | `100` MB |
| Git auto-commit | Enabled |
| Skip conversations | Disabled |
| Include standalone | Disabled |
| Full sync | Disabled (incremental) |
| Verbose output | Disabled |

## Finding Your Org UUID

### Method 1: Auto-discovery

```bash
./claude_sync.py --list-orgs
```

Lists all organizations your browser session has access to.

### Method 2: Browser DevTools

1. Open [claude.ai](https://claude.ai) and log in
2. Open browser DevTools (F12)
3. Go to the **Network** tab
4. Click on any project or refresh the page
5. Look for requests to `https://claude.ai/api/organizations/`
6. Copy the UUID from the URL (format: `f3e5048f-1380-4436-83cf-085832fff594`)

### Method 3: Save to Environment

```bash
echo "CLAUDE_ORG_UUID=your-uuid-here" > ~/.claude-sync.env
```

Then run `./claude_sync.py` without arguments.
