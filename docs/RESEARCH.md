# Claude Web App ↔ Local Sync: Research & Plan

## Executive Summary

This document captures research findings and planning for a tool to sync Claude web app projects with local storage for use with Claude Code.

**Key Finding**: Write operations to Claude.ai projects are **NOT possible** via API - only read operations work. This fundamentally constrains the architecture to **one-way sync (web → local)** with optional manual flagging for changes that need to be pushed back via the web UI.

______________________________________________________________________

## 1. Research Findings

### 1.1 API Capabilities

#### What's POSSIBLE (Read Operations)

| Endpoint | Description |
|----------|-------------|
| `GET /api/organizations/{org}/projects` | List all projects |
| `GET /api/organizations/{org}/projects/{pid}` | Project metadata + prompt_template |
| `GET /api/organizations/{org}/projects/{pid}/docs?tree=true` | Project documents |
| `GET /api/organizations/{org}/projects/{pid}/conversations?tree=true` | Project conversation list |
| `GET /api/organizations/{org}/chat_conversations/{cid}` | Full conversation history |

#### What's NOT POSSIBLE (No Write Endpoints Found)

- Create/update projects
- Update project instructions (prompt_template)
- Create/update/delete project docs
- Any project mutation operations

**Conclusion**: Two-way sync is not feasible without browser automation or manual intervention.

#### Authentication

- Requires `sessionKey` cookie from browser (Edge/Chrome)
- Session keys expire frequently
- Uses `browser-cookie3` library for extraction

### 1.2 Data Structures & Metadata

From analysis of existing exports:

**Projects** (`projects.json`):

```json
{
  "uuid": "...",
  "name": "Project Name",
  "description": "...",
  "prompt_template": "...",  // Project instructions
  "created_at": "2024-06-28T13:27:50.549422+00:00",
  "updated_at": "2024-12-10T12:22:04.523363+00:00",
  "is_private": true,
  "creator": {"uuid": "...", "full_name": "..."},
  "docs": [
    {
      "uuid": "...",
      "filename": "doc.md",
      "content": "...",
      "created_at": "..."  // NOTE: NO updated_at on docs!
    }
  ]
}
```

**Conversations**:

```json
{
  "uuid": "...",
  "name": "Conversation Title",
  "created_at": "...",
  "updated_at": "...",
  "chat_messages": [
    {
      "uuid": "...",
      "text": "",  // NOTE: Always empty - actual content is in 'content' array
      "content": [
        {"type": "text", "text": "actual message content"},
        {"type": "thinking", "thinking": "Claude's thinking (if extended thinking enabled)"}
      ],
      "sender": "human|assistant",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

**Key Metadata for Incremental Sync**:

- `uuid` on all entities (stable identifiers)
- `updated_at` on projects & conversations (enables change detection)
- `created_at` timestamps (enables staleness detection)
- **LIMITATION**: Docs only have `created_at`, not `updated_at` → need content hashing

### 1.3 Incremental Sync Feasibility

| What | Change Detection | Method |
|------|------------------|--------|
| New conversations/projects | ✅ Easy | UUID comparison |
| Modified conversations/projects | ✅ Easy | `updated_at` comparison |
| Deleted items | ✅ Easy | UUID disappeared |
| Modified docs | ⚠️ Workaround | Content hashing (SHA256) |
| Which specific message changed | ❌ Not possible | Must re-download conversation |

**Efficiency**: 95-97% bandwidth reduction with incremental sync:

- Full sync: 29.7 MB, 30-60s
- Daily incremental: ~0.5 MB, 2-5s
- Weekly incremental: ~2 MB, 5-10s

### 1.4 Volume Analysis (Your Data)

- 13 projects
- 619 conversations, ~7000 messages
- Date range: 2024-02-08 to 2025-04-03
- Total export size: ~31 MB (mostly conversations)

### 1.5 Claude Code Integration Patterns

**Recommended Hierarchy** (from official docs):

1. **CLAUDE.md imports** - `@path/to/file.md` syntax for external references
1. **Skills** (`.claude/skills/`) - Auto-discovered by description matching
1. **Slash Commands** (`.claude/commands/`) - User-invoked templates
1. **MCP Servers** (`.mcp.json`) - Programmatic access to data

**Best Practice for Synced Content**:

```
project/
├── CLAUDE.md                    # Main instructions, imports synced content
├── .claude/
│   └── skills/
│       └── webapp-context/      # Synced web app content as a skill
│           ├── SKILL.md
│           └── docs/
└── ~/.local/share/claude-sync/  # Raw synced data
    └── apart-lab-general/
        ├── CLAUDE.md            # Project instructions
        └── docs/
```

______________________________________________________________________

## 2. Use Cases (Prioritized)

### Tier 1: High Value, Low Effort (MVP)

| Use Case | Value | Effort | Notes |
|----------|-------|--------|-------|
| **Access project docs locally** (style guides, process docs) | Very High | Low | Direct file sync |
| **Search conversation history** | High | Low | Export to searchable format |
| **Project instructions available in Claude Code** | High | Low | Export as CLAUDE.md |

### Tier 2: High Value, Medium Effort

| Use Case | Value | Effort | Notes |
|----------|-------|--------|-------|
| **Incremental sync** (only fetch changes) | Medium | Medium | Track `updated_at` |
| **Reference past conversations** in Claude Code | Medium | Medium | Need good organization |
| **Auto-generate skills from project docs** | Medium | Medium | Template generation |

### Tier 3: Aspirational (High Effort or Blocked)

| Use Case | Value | Effort | Notes |
|----------|-------|--------|-------|
| **Two-way sync** (local → web) | Very High | **Blocked** | No write API |
| **Continue Claude Code conv in web app** | High | **Blocked** | Different systems |
| **Agentic doc review/cleanup** | Medium | High | Separate project |

______________________________________________________________________

## 3. Architecture Design

### 3.1 Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                      Claude Web App                              │
│  (Projects, Docs, Conversations, Instructions)                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ READ ONLY (sessionKey auth)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     claude-sync CLI                              │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │ Fetcher       │  │ Differ        │  │ Transformer   │       │
│  │ (API client)  │  │ (Change det.) │  │ (Format conv) │       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
│                              │                                   │
│                     ┌────────┴────────┐                         │
│                     │ Sync State DB   │                         │
│                     │ (SQLite/JSON)   │                         │
│                     └─────────────────┘                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Local Storage                                 │
│  ~/.local/share/claude-sync/                                     │
│  ├── index.json              # Manifest with sync metadata       │
│  ├── apart-lab-general/                                          │
│  │   ├── CLAUDE.md           # Project instructions              │
│  │   ├── meta.json           # Project metadata                  │
│  │   ├── docs/               # Project documents                 │
│  │   └── conversations/      # (Optional) Conversation exports   │
│  └── ...                                                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Claude Code Integration                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ~/.claude/CLAUDE.md                                        │  │
│  │ # Synced Web App Projects                                  │  │
│  │ @~/.local/share/claude-sync/apart-lab-general/CLAUDE.md    │  │
│  │ @~/.local/share/claude-sync/email-style/CLAUDE.md          │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  OR via MCP server for dynamic access                            │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Sync State Management

To enable incremental sync and prevent overwrites:

```json
// ~/.local/share/claude-sync/index.json
{
  "last_sync": "2025-01-15T10:30:00Z",
  "org_id": "...",
  "projects": {
    "uuid-1": {
      "name": "Apart Lab General",
      "last_synced_at": "2025-01-15T10:30:00Z",
      "remote_updated_at": "2024-12-10T12:22:04Z",
      "local_path": "apart-lab-general/",
      "local_modified": false,  // Flag for local changes
      "docs_count": 20,
      "conversations_count": 45
    }
  }
}
```

### 3.3 Conflict Handling Strategy

Since we can't push changes back:

1. **Track local modifications** via file hashes or mtime
1. **On sync, if local modified**:
   - Create backup: `CLAUDE.md.local-backup-{timestamp}`
   - Warn user: "Local changes exist - review before overwriting"
   - Optionally: show diff
1. **Flag for manual push**: Create `.needs-push` marker files
1. **Accept imperfection**: Some manual web UI work will be needed

______________________________________________________________________

## 4. Implementation Phases

### Phase 1: MVP (80% Value) - "Fetch & Organize" [COMPLETED]

**Goal**: Get web app project content into Claude Code-friendly local structure

**Features**:

- [x] Direct fetch to organized directory structure (no ZIP intermediate)
- [x] Generate CLAUDE.md for each project from `prompt_template`
- [x] Create index/manifest for discoverability
- [x] CLI: `claude-sync sync <org-id>` with typer framework

**Output Structure**:

```
~/.local/share/claude-sync/
├── index.json
├── apart-lab-general/
│   ├── CLAUDE.md           # From prompt_template
│   ├── meta.json
│   └── docs/
│       ├── email-style-guide.md
│       └── ...
```

**Integration**: Add to `~/.claude/CLAUDE.md`:

```markdown
# Synced Web App Projects
@~/.local/share/claude-sync/apart-lab-general/CLAUDE.md
```

### Phase 2: Incremental Sync - "Smart Updates" [COMPLETED]

**Goal**: Only fetch what changed

**Features**:

- [x] Store sync state (last sync time, remote `updated_at` in `.sync-state.json`)
- [x] Compare timestamps before fetching full content
- [x] Fetch only modified projects/docs
- [x] CLI: incremental sync by default, `--full` flag to force full sync

**API Strategy**:

1. Fetch project list (lightweight)
1. Compare `updated_at` with stored state
1. Only fetch full content for changed projects

### Phase 3: Local Change Tracking - "Safe Sync" [PARTIALLY COMPLETED]

**Goal**: Don't lose local edits

**Features**:

- [x] Hash tracking for documents (in `.sync-state.json`)
- [x] Backup mechanism (`.backup/` directory with timestamped files)
- [x] CLI: `claude-sync status` (show local status and remote changes)
- [ ] Warn before overwriting modified files (not implemented - backups are automatic)
- [ ] `.needs-push` markers for manual sync reminders (N/A - read-only sync)

### Phase 4: Enhanced Integration - "Deep Claude Code"

**Goal**: Richer Claude Code experience

**Options** (choose based on need):

- [ ] MCP server for dynamic project access
- [ ] Auto-generate skills from project docs
- [ ] Conversation search tool
- [ ] Slash commands from project templates

### Phase 5 (Separate Project?): Agentic Review - "Doc Hygiene"

**Goal**: Intelligent content management

**Features**:

- [ ] Detect redundant/overlapping docs
- [ ] Flag potentially outdated content (by age, similarity)
- [ ] Suggest consolidation
- [ ] Works on any doc corpus (not just web app syncs)

______________________________________________________________________

## 5. Technical Considerations

### 5.1 Known Issues / Gotchas

| Issue | Mitigation |
|-------|------------|
| Forward slashes in doc titles break filenames | Robust sanitization (not just `slugify`) |
| Session keys expire frequently | Clear error message, re-auth instructions |
| Large conversation history (30MB+) | Optional: skip conversations, or only recent |
| Rate limiting (undocumented) | Respect reasonable delays, parallel with limits |
| Regional restrictions | VPN may be needed |

### 5.2 Filename Sanitization

Need to handle:

- Forward slash `/`
- Backslash `\`
- Colon `:`
- Asterisk `*`
- Question mark `?`
- Quotes `"` `'`
- Angle brackets `<` `>`
- Pipe `|`
- NULL bytes
- Reserved names (Windows: CON, PRN, etc.)
- Leading/trailing spaces/dots

### 5.3 Testing Strategy

- Unit tests for transformers/sanitizers
- Integration tests with mock API responses
- "Red team" agent pass for edge cases
- Manual testing with real data (your exports)

______________________________________________________________________

## 6. Open Questions

1. **Conversation sync depth**: All conversations or just recent N? Project-associated only?
1. **Storage location**: `~/.local/share/claude-sync/` vs project-local?
1. **MCP vs static files**: Is dynamic MCP access worth the complexity?
1. **Multi-org support**: Handle multiple organizations?
1. **Automation**: Run on schedule (launchd/cron) or manual only?

______________________________________________________________________

## 7. Next Steps

1. **Decide on Phase 1 scope** - What's the minimal useful version?
1. **Enhance existing gist** or **start fresh**?
1. **Choose storage location** and integration pattern
1. **Implement MVP** with good logging/metadata for future phases

______________________________________________________________________

## Appendix: Existing Assets

- **Gist**: <https://gist.github.com/jas-ho/f95abd89d4e007eac9ee821d7c2a3d0b>
- **Local export**: Local directory with exported Claude data
- **Processing scripts**: `process_projects.py`, `extract_metadata.py`
- **Sample processed**: `processed_projects_DONE/`
