# Incremental Sync Testing Guide

This document provides test plans for verifying incremental sync functionality with actual changes on claude.ai.

## Prerequisites

- Have claude-sync installed and working
- Be logged into claude.ai in your browser
- Have at least one project with documents and conversations

## Test 1: Baseline Full Sync

```bash
# Start fresh
rm -rf /tmp/claude-sync-test

# Run full sync
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v

# Verify output
ls /tmp/claude-sync-test/
cat /tmp/claude-sync-test/index.json
```

**Expected**: All projects synced, conversations included, git repo initialized.

## Test 2: Incremental Sync (No Changes)

```bash
# Run sync again without changes
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v
```

**Expected**:

- Output shows "Skipping <project>: unchanged" for all projects
- Summary shows "0 updated, N unchanged"
- Git shows "No changes to commit"

## Test 3: Project Metadata Change

1. Go to claude.ai web UI
1. Open a project (e.g., "Test Project")
1. Edit the project description or instructions
1. Save changes

```bash
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v
```

**Expected**:

- Only the modified project shows "Syncing <project>: updated"
- Other projects show "Skipping: unchanged"
- CLAUDE.md in that project folder is updated
- Git shows a new commit with the changes

## Test 4: Document Content Change

1. Go to claude.ai web UI
1. Open a project
1. Edit an existing document's content
1. Save changes

```bash
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v
```

**Expected**:

- Project shows "Syncing: updated" (doc hash changed)
- Document file is updated with new content

## Test 5: New Document Added

1. Go to claude.ai web UI
1. Open a project
1. Click "Add document" and add a new file
1. Save

```bash
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v
```

**Expected**:

- Project resyncs
- New document appears in `docs/` folder
- docs_count in index.json increases

## Test 6: Conversation Update

1. Go to claude.ai web UI
1. Open a project
1. Open an existing conversation
1. Send a new message and get a response

```bash
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v
```

**Expected**:

- Project resyncs (or just that conversation, depending on implementation)
- Conversation file updated with new messages
- conversations/index.json shows updated message_count

## Test 7: New Conversation

1. Go to claude.ai web UI
1. Open a project
1. Start a new conversation
1. Have a brief exchange

```bash
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v
```

**Expected**:

- New conversation file appears in `conversations/`
- conversations/index.json includes new conversation
- Other conversations show "skipped" in verbose output

## Test 8: --full Flag Verification

```bash
# First, normal incremental (should skip all)
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test -v

# Now force full sync
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test --full -v
```

**Expected**:

- With `--full`: All projects synced, all conversations fetched
- Without `--full`: Only changed items synced

## Test 9: --skip-conversations Flag

```bash
./claude_sync.py <org-uuid> -o /tmp/claude-sync-test --skip-conversations -v
```

**Expected**:

- Projects sync but conversations folder not created/updated
- Much faster sync time

## Manual Test Results (2025-12-07)

Comprehensive testing session validating incremental sync detection across all change scenarios:

| # | Scenario | Result | Notes |
|---|----------|--------|-------|
| 1 | Conversation message added | ✅ Fixed | Detected independently (bug 655 fixed) |
| 2 | New doc added | ✅ Pass | Doc count change detected |
| 3 | Duplicate filename doc | ✅ Pass | Handled with `_1` suffix |
| 4 | New conversation only | ✅ Fixed | Detected independently (bug 655 fixed) |
| 5 | Instructions changed | ✅ Pass | `updated_at` changed |
| 6 | Doc/convo deleted | ⚠️ Partial | Orphan files remain (tracked in daw) |
| 7 | Conversation renamed | ✅ Fixed | Old file deleted (bug ivi fixed) |
| 8 | Project renamed | ✅ Fixed | Old folder deleted (bug ivi fixed) |

### Key Findings

#### What updates project `updated_at`

- Project name change ✓
- Project instructions (prompt_template) change ✓

#### What does NOT update project `updated_at`

- New conversation
- Message added to conversation
- Conversation renamed
- Doc changes (detected via content hash instead)

### Bugs Fixed in This Session

- `claude-sync-655`: Conversations now checked independently (even when project `updated_at` unchanged)
- `claude-sync-ivi`: Renames handled gracefully (old files/folders deleted automatically)
- `claude-sync-l4u`: Atomic writes for state files (prevents corruption on interruption)
- `claude-sync-1j3`: Safe timestamp comparisons (handles None values correctly)

## Known Limitations

### Deleted Items (Tracked in claude-sync-daw)

If you delete a project/document/conversation on claude.ai:

- Orphaned files remain in local storage
- Not automatically deleted (safety first)
- Manual cleanup required

**Future enhancement**: Orphan detection and cleanup with confirmation prompt.

### Deleted Projects

- Deleted projects are marked as "orphaned" in index.json
- Local files are NOT deleted (safety first)
- Manual cleanup required

## Troubleshooting

### "Session expired" errors

- Re-login to claude.ai in your browser
- Close and reopen browser to refresh cookies

### Cloudflare blocks

- The tool uses curl_cffi with Chrome impersonation
- If blocked, try waiting a few minutes
- Make sure your browser is actually logged in

### Sync state issues

- Delete `.sync-state.json` in output dir to force fresh sync
- Or use `--full` flag
