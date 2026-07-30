# claude-sync

`CLAUDE.md` and `AGENTS.md` are identical agent instructions. Keep them synchronized.

This project uses [bd (beads)](https://github.com/steveyegge/beads) for all issue tracking. Do not create markdown TODO lists or use a second tracker.

## Project Purpose

Sync Claude web app projects (claude.ai) to local storage for use with Claude Code.

**Key Use Cases:**

- Access project docs locally (style guides, process docs)
- Search conversation history
- Make project instructions available in Claude Code

## Architecture

Single UV script (`claude_sync.py`) with inline dependencies:

- `curl_cffi` - API calls (Cloudflare bypass)
- `browser-cookie3` - Session extraction from Edge/Chrome
- `tqdm` - Progress display

**Output**: Directory structure (not ZIP) for git tracking:

```text
<output-dir>/
├── .sync-state.json        # Internal sync state (timestamps, hashes)
├── index.json              # Manifest with sync metadata
├── _standalone/            # Standalone conversations (not in projects)
│   ├── index.json          # Standalone conversation manifest
│   └── <conversation-name>.md  # Individual conversations (named by title)
└── <project-slug>/
    ├── CLAUDE.md           # Project instructions (from prompt_template)
    ├── meta.json           # Project metadata
    ├── docs/               # Project documents
    └── conversations/      # Project conversation history
        ├── index.json      # Conversation manifest
        └── <conversation-name>.md  # Individual conversations (named by title)
```

## Status Command

Check sync health without running a full sync:

```bash
# Local status (no auth required)
./claude_sync.py status

# Check for remote changes
./claude_sync.py status --remote

# Thorough doc checking (slow)
./claude_sync.py status --remote --check-docs
```

**Local status shows:**

- Last sync time and age
- Project, document, conversation counts
- Recently active projects
- Integrity check (directories match manifest)

**Remote comparison (`--remote`) detects:**

- New projects on claude.ai
- Modified project instructions
- New/modified conversations
- Deleted projects

**Document checking (`--check-docs`):**

- Detects new, modified, or deleted documents
- Requires `--remote` flag
- May be slow as it fetches all document metadata

## Technical Constraints

- **Read-only API**: No write endpoints for claude.ai projects exist
- **Auth**: Browser cookie extraction (sessionKey, cf_clearance)
- **Incremental sync**: Use `updated_at` timestamps + content hashing for docs

## Development Guidelines

- **Command timeouts**: In Claude Code, use the Bash tool's `timeout` parameter instead of wrapping commands with `timeout`; shell wrappers do not match its prefix-based permission rules. In other agent hosts, prefer the execution tool's native timeout when available.
- Single-file UV script with inline deps for portability
- Configurable output location (default: `~/.local/share/claude-sync/`)
- User-agnostic: No hardcoded paths or personal data
- Robust filename sanitization (cross-platform)

## Testing Approach

**Use local `test-data/` directory** instead of `~/.local/share/claude-sync/` to avoid permission prompts:

```bash
# Create test directory (gitignored)
mkdir -p ./test-data

# Copy real sync data for testing (one-time setup)
cp ~/.local/share/claude-sync/index.json ./test-data/
cp ~/.local/share/claude-sync/.sync-state.json ./test-data/

# Test with local directory
uv run ./claude_sync.py status -o ./test-data

# For remote tests, you can still use -o ./test-data for output
# but remote API calls will work normally
```

**Why this matters:**

- Avoids repeated permission prompts for `~/.local/share/` operations
- `test-data/` is in `.gitignore` so test artifacts aren't committed
- Sub-agents can run tests without needing user approval

## Key Files

- `claude_sync.py` - Main script (single-file UV script with inline dependencies)
- `docs/RESEARCH.md` - Full API research and planning
- `docs/API_CONTRACT.md` - API response structure assumptions
- `docs/IMPLEMENTATION_NOTES.md` - Implementation findings and edge cases
- `reference/` - Old scripts and gist reference

## Issue Tracking

```bash
bd ready --json                              # See unblocked work
bd list --json                               # List all issues
bd show <id> --json                          # Show issue details
bd create "Issue title" -t task -p 2 --json # Create work
bd update <id> --status in_progress --json   # Claim work
bd close <id> --reason "Done" --json         # Complete work
```

Use `bd` for all task tracking, link discovered work with `discovered-from`, and commit `.beads/issues.jsonl` with the related code changes.
