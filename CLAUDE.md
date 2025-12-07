# claude-sync

**Note**: This project uses [bd (beads)](https://github.com/steveyegge/beads) for issue tracking. Use `bd` commands instead of markdown TODOs. See AGENTS.md for workflow details.

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
```
<output-dir>/
├── index.json              # Manifest with sync metadata
└── <project-slug>/
    ├── CLAUDE.md           # Project instructions (from prompt_template)
    ├── meta.json           # Project metadata
    └── docs/               # Project documents
```

## Technical Constraints

- **Read-only API**: No write endpoints for claude.ai projects exist
- **Auth**: Browser cookie extraction (sessionKey, cf_clearance)
- **Incremental sync**: Use `updated_at` timestamps + content hashing for docs

## Development Guidelines

- Single-file UV script with inline deps for portability
- Configurable output location (default: `~/.local/share/claude-sync/`)
- User-agnostic: No hardcoded paths or personal data
- Robust filename sanitization (cross-platform)

## Key Files

- `claude_sync.py` - Main script (to be created)
- `docs/RESEARCH.md` - Full API research and planning
- `reference/` - Old scripts and gist reference

## Issue Tracking

```bash
bd ready          # See unblocked work
bd list           # All issues
bd show <id>      # Issue details
```
