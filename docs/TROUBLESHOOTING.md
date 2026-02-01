# Troubleshooting Guide

This guide covers common issues with claude-sync and their solutions. Most problems fall into a few categories: authentication/cookies, API limits, and local file issues.

---

## Cookie Extraction Issues

### Permission denied accessing Edge cookies

**Error:** `Permission denied accessing edge cookies`

**Solutions:**

1. Close your browser completely
2. On macOS: Grant your terminal/IDE access in **System Preferences > Security & Privacy > Privacy > Full Disk Access**
3. Retry the sync

### Browser cookie database is locked

**Error:** `Browser cookie database is locked`

**Solution:** Close your browser completely and retry.

### Missing sessionKey cookie

**Error:** `Missing required cookie(s): sessionKey`

**Solutions:**

1. Log into [claude.ai](https://claude.ai) in your browser
2. Refresh the page to ensure cookies are written
3. Retry the sync

---

## Session Expiry

**Error:** `Session expired or invalid`

**Solutions:**

1. Open [claude.ai](https://claude.ai) in your browser
2. Log out and log back in
3. Retry the sync

Session cookies expire periodically. Re-authenticating in your browser refreshes them.

---

## Rate Limiting

**Error:** `Rate limited by Claude.ai`

**Solutions:**

- Wait a few minutes and retry
- Reduce sync frequency if running on a schedule

The sync tool includes automatic delays between requests, but syncing many large projects may still trigger rate limits.

---

## Cloudflare Blocking

**Error:** `API returned HTML instead of JSON` or `Cloudflare blocked the request`

**Solutions:**

1. Wait a few minutes
2. Verify [claude.ai](https://claude.ai) is accessible in your browser
3. Retry

This usually resolves itself. The tool uses browser impersonation via `curl_cffi` to minimize blocking.

---

## Concurrent Sync Errors

**Error:** `Another sync is running (PID: 12345)`

**Solutions:**

- **If another sync is genuinely running:** Wait for it to complete
- **If the process died (stale lock):** Delete the lock file:
  ```bash
  rm ~/.local/share/claude-sync/.claude-sync.lock
  ```

---

## Disk Space

**Error:** `Insufficient disk space`

**Solutions:**

- Free up disk space, or
- Use a different output directory with more space:
  ```bash
  ./claude_sync.py sync -o /path/with/more/space
  ```

---

## File and Message Limits

### Large files skipped

**Warning:** `Skipping doc '...': 12.5MB exceeds 10MB limit`

**Explanation:** Documents larger than 10MB are automatically skipped to prevent memory exhaustion.

**Workaround:** Download large files manually from the [claude.ai](https://claude.ai) web interface.

### Conversation message limits

**Warning:** `Skipping conversation '...': 15000 messages exceeds 10000 limit`

**Explanation:** Conversations with more than 10,000 messages are skipped to prevent excessive API usage and memory consumption.

---

## Common Errors Reference

| Error | Cause | Solution |
|-------|-------|----------|
| `FileNotFoundError: Resource not found` | Project/doc deleted remotely during sync | Normal - item was deleted, sync continues |
| `Slug collision` | Two projects generated same directory name | Manually rename one project directory |
| `Invalid JSON in API response` | Network corruption or API change | Retry; report if persistent |
| `Git not found in PATH` | Git not installed | Install git, or use `--no-git` flag |
| `404` on login despite valid session | Account mismatch (logged into org A, syncing org B) | Log into the correct account in your browser |

---

## Still Having Issues?

1. **Check the README** for setup and usage details
2. **Run with verbose output** to see what's happening:
   ```bash
   ./claude_sync.py sync --verbose
   ```
3. **Check API_CONTRACT.md** if you suspect API changes
4. **File an issue** with the error message and steps to reproduce
