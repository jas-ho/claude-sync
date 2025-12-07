# Implementation Handoff for claude-sync

## Quick Start for Implementing Agent

```bash
cd /Users/jason/Code/claude-sync
bd ready                    # See unblocked tasks
bd show claude-sync-8co     # MVP epic with full context
bd show claude-sync-8co.3   # First task: script skeleton
```

## Project Goal

Create a single-file Python script (`claude_sync.py`) that syncs Claude web app projects to local storage for use with Claude Code.

## Key Requirements

1. **Single UV script** with inline dependencies:
   ```python
   #!/usr/bin/env -S uv run --script
   # /// script
   # requires-python = ">=3.12"
   # dependencies = ["curl_cffi", "tqdm", "browser-cookie3"]
   # ///
   ```

2. **Output structure**:
   ```
   ~/.local/share/claude-sync/
   ├── index.json
   └── <project-slug>-<uuid>/
       ├── CLAUDE.md           # From prompt_template
       ├── meta.json
       ├── docs/
       └── conversations/      # Project conversations
   ```

3. **CLI interface**:
   ```bash
   ./claude_sync.py <ORG_UUID> -o <output-dir> --browser edge
   ```

## Critical Files to Read First

1. `bd show claude-sync-8co` - Full MVP requirements
2. `docs/RESEARCH.md` - API research, data structures, gotchas
3. `reference/GIST_REFERENCE.md` - Original gist to build from

## High-Risk Areas (Read Task Descriptions!)

- `claude-sync-8co.4` - Cookie extraction has macOS Keychain issues
- `claude-sync-8co.5` - API is undocumented, may change
- `claude-sync-8co.6` - Filename sanitization has collision edge cases
- `claude-sync-8co.10` - Partial sync failures need atomic writes

## Workflow

1. Claim task: `bd update <id> --status in_progress`
2. Implement
3. Test with real org UUID (user will provide)
4. Close task: `bd close <id> --reason "Completed: <summary>"`
5. Commit code + `.beads/issues.jsonl` together
6. If you discover new issues: `bd create "..." --deps discovered-from:<current-task>`

## API Endpoints

```
Base: https://claude.ai/api/organizations/{org}/

GET projects                                    # List projects
GET projects/{pid}                              # Project metadata
GET projects/{pid}/docs?tree=true               # Project docs
GET projects/{pid}/conversations?tree=true      # Project conversations
GET chat_conversations/{cid}?rendering_mode=messages&render_all_tools=true
```

## Testing

User's org has ~13 projects, ~20 docs each. Test with real data.
Provide clear instructions if you need the org UUID.

## Git Commits

Commit regularly with descriptive messages. Include `.beads/issues.jsonl` with code changes.
