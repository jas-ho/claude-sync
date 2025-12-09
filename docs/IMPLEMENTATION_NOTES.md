# Implementation Notes & Observations

Notes collected during implementation for sanity check review.

## API Findings

### Cookie/Auth
- `cf_clearance` cookie alone isn't enough - Cloudflare uses TLS fingerprinting
- **Solution**: `curl_cffi` with `impersonate="chrome"` bypasses Cloudflare
- Standard `requests` library and `curl` both get blocked

### Endpoints
- `/api/organizations/{org}/projects` - returns list, but **NO prompt_template**
- `/api/organizations/{org}/projects/{pid}` - returns full details including prompt_template
- **Gotcha**: Must fetch each project individually to get instructions
- Doc filename key is `file_name` (with underscore), not `filename`

### Bootstrap
- `/api/bootstrap` returns user info including organization memberships
- Works for org auto-discovery

## Output Structure

```
~/.local/share/claude-sync/
├── .sync-state.json       # Internal sync state (timestamps, hashes)
├── index.json             # Project manifest
├── _standalone/           # Standalone conversations (not in projects)
│   ├── index.json         # Standalone conversation manifest
│   └── <conversation-name>.md  # Individual conversations (named by title)
└── <project-slug>/
    ├── CLAUDE.md          # prompt_template with frontmatter
    ├── meta.json          # project metadata
    ├── docs/              # project documents
    │   └── *.md
    └── conversations/     # project conversation history
        ├── index.json     # conversation manifest
        └── <conversation-name>.md  # individual conversations (named by title)
```

## Edge Cases Handled

### Filename Sanitization
- Invalid chars: `<>:"/\|?*` and control chars → replaced with `-`
- Windows reserved names (CON, PRN, etc.) → prefixed with `_`
- Collisions after sanitization → numeric suffix `_1`, `_2`, etc.
- Case-insensitive collision check (macOS HFS+)
- Long names → truncated with hash suffix

### Missing Data
- No prompt_template → generates minimal CLAUDE.md with project name
- No filename on doc → defaults to `untitled.md`
- Missing extension → adds `.md`

## Recent Features Added

### Status Command
- Local status check (no auth required): sync age, counts, integrity check
- Remote status check (`--remote`): detects new/modified/deleted projects and conversations
- Document checking (`--check-docs`): thorough check for document changes (requires `--remote`)

### Error Handling Improvements
- Failed project tracking: sync continues if individual projects fail
- Stale lock detection: warns if lock file exists but process is dead
- Better error messages with recovery instructions

### Standalone Conversations
- Support for syncing conversations not attached to any project
- `--include-standalone` flag to enable
- Saved to `_standalone/` directory

## Known Issues / TODOs

1. **Multiple orgs with same name**: User has two "Apart Research" orgs - no way to distinguish except by UUID

## Performance

- ~18 seconds for 16 projects
- 2 API calls per project (details + docs)
- 0.2s delay between requests

## Testing Observations

- Real sync tested with user's 16 projects
- Docs have meaningful names (not all "untitled")
- prompt_template correctly extracted when present
- Progress bar (tqdm) works correctly

## Sanity Check Results (2025-12-07)

**Verified:**
- [x] 16 projects in index.json matches 16 directories
- [x] CLAUDE.md content matches web UI prompt_template
- [x] Projects without instructions show fallback message
- [x] Doc count correct (e.g., apart-lab has 23 docs)
- [x] Special chars in filenames handled (`:`, `?`, `-` → hyphen)
- [x] Collision handling works (`_1` suffix added)
- [x] All output is text (ASCII/JSON), git-trackable
- [x] ~18s for 16 projects (< 2 min target)

**Example filename sanitization:**
- `AGI 2.2 - -Long- timelines to advanced AI...` → preserved
- `Why do people disagree about when powerful AI will arrive?` → `?` removed
- Duplicates → `ai_emotional_dependency_research_strategy_1.md` (added `_1`)
