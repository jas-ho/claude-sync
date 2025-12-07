#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["curl_cffi", "tqdm", "browser-cookie3"]
# ///
"""
claude-sync: Sync Claude web app projects to local storage.

Fetches projects, docs, and optionally conversations from claude.ai
and organizes them into a local directory structure for Claude Code integration.
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import logging
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from curl_cffi import requests

# Constants
# Use XDG-compliant data location (not ~/.claude which is for Claude Code config)
DEFAULT_OUTPUT_DIR = Path.home() / ".local" / "share" / "claude-sync"
API_BASE = "https://claude.ai/api/organizations"
SUPPORTED_BROWSERS = ["edge", "chrome"]

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
log = logging.getLogger(__name__)

# Global flag for graceful interrupt handling
_interrupted = False


def _handle_interrupt(signum, frame):
    """Handle interrupt signals gracefully."""
    global _interrupted
    if _interrupted:
        # Second interrupt - force exit
        log.warning("\nForce exit requested")
        sys.exit(130)
    _interrupted = True
    log.warning("\nInterrupt received, finishing current project...")


@dataclass
class Config:
    """Runtime configuration for sync operation."""

    org_uuid: str | None
    output_dir: Path
    browser: str
    skip_conversations: bool = False  # Default: sync conversations
    verbose: bool = False
    list_orgs: bool = False
    full_sync: bool = False  # Force full sync, ignore cached state
    auto_commit: bool = True  # Auto git-init and commit after sync
    project_filter: str | None = None  # Filter to single project (UUID or name substring)


def get_config_from_env() -> dict:
    """Load configuration from environment variables or .env file."""
    config = {}

    # Check for .env file in current directory or home
    env_paths = [
        Path.cwd() / ".env",
        Path.cwd() / ".claude-sync.env",
        Path.home() / ".claude-sync.env",
    ]

    for env_path in env_paths:
        if env_path.exists():
            log.debug(f"Loading config from {env_path}")
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        config[key.strip()] = value.strip().strip("\"'")
            break

    # Environment variables override file
    if org := os.environ.get("CLAUDE_ORG_UUID"):
        config["CLAUDE_ORG_UUID"] = org

    return config


def sanitize_sensitive_data(text: str) -> str:
    """Remove potential credentials from text for safe logging.

    Redacts:
    - Session keys and tokens (long alphanumeric strings)
    - Anything that looks like a secret
    """
    import re
    # Redact sessionKey specifically
    text = re.sub(
        r'(sessionKey["\']?\s*[:=]\s*["\']?)[a-zA-Z0-9_-]{20,}',
        r'\1[REDACTED]',
        text,
        flags=re.IGNORECASE
    )
    # Redact any very long alphanumeric strings (likely tokens)
    text = re.sub(r'\b[a-zA-Z0-9_-]{50,}\b', '[REDACTED-TOKEN]', text)
    return text


# =============================================================================
# Cookie Extraction (Task 8co.4)
# =============================================================================


class CookieExtractionError(Exception):
    """Raised when cookie extraction fails."""

    pass


def get_session_cookies(browser: str) -> "http.cookiejar.CookieJar":
    """Extract session cookies from browser.

    Args:
        browser: Browser to extract from ('edge' or 'chrome')

    Returns:
        CookieJar with session cookies

    Raises:
        CookieExtractionError: If cookie extraction fails
    """
    import browser_cookie3

    domain = "claude.ai"
    required_cookies = {"sessionKey"}

    try:
        if browser == "edge":
            log.debug("Extracting cookies from Microsoft Edge...")
            cj = browser_cookie3.edge(domain_name=domain)
        elif browser == "chrome":
            log.debug("Extracting cookies from Google Chrome...")
            cj = browser_cookie3.chrome(domain_name=domain)
        else:
            raise CookieExtractionError(f"Unsupported browser: {browser}")
    except PermissionError as e:
        raise CookieExtractionError(
            f"Permission denied accessing {browser} cookies.\n"
            f"Try closing {browser} completely and retry.\n"
            f"On macOS, you may need to grant Terminal/IDE access in "
            f"System Preferences > Security & Privacy > Privacy > Full Disk Access.\n"
            f"Original error: {sanitize_sensitive_data(str(e))}"
        ) from e
    except Exception as e:
        # browser-cookie3 can raise various exceptions
        error_str = str(e).lower()
        if "locked" in error_str or "database" in error_str:
            raise CookieExtractionError(
                f"Browser cookie database is locked.\n"
                f"Close {browser} completely and retry."
            ) from e
        raise CookieExtractionError(
            f"Failed to extract cookies from {browser}: {sanitize_sensitive_data(str(e))}"
        ) from e

    # Check for required cookies
    cookie_names = {cookie.name for cookie in cj}
    log.debug(f"Found cookies: {cookie_names}")

    missing = required_cookies - cookie_names
    if missing:
        raise CookieExtractionError(
            f"Missing required cookie(s): {missing}\n"
            f"Please log into claude.ai in {browser} and retry.\n"
            f"If you recently logged in, try refreshing the page first."
        )

    # Check if session might be expired (sessionKey exists but is short/invalid format)
    for cookie in cj:
        if cookie.name == "sessionKey" and len(cookie.value) < 20:
            raise CookieExtractionError(
                "Session key appears invalid (too short).\n"
                "Please log into claude.ai in your browser and retry."
            )

    log.info(f"Extracted {len(cookie_names)} cookie(s) from {browser}")
    return cj


# =============================================================================
# API Client (Task 8co.5)
# =============================================================================


class APIError(Exception):
    """Raised when API request fails."""

    pass


class SessionExpiredError(APIError):
    """Raised when session has expired."""

    pass


# Realistic browser headers
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://claude.ai/",
    "Origin": "https://claude.ai",
}

REQUEST_TIMEOUT = 30  # seconds
REQUEST_DELAY = 0.2  # seconds between requests


def create_session(cookie_jar: "http.cookiejar.CookieJar") -> "requests.Session":
    """Create authenticated requests session.

    Args:
        cookie_jar: CookieJar with session cookies

    Returns:
        Configured curl_cffi Session with browser impersonation
    """
    from curl_cffi import requests

    # Convert cookie jar to dict for curl_cffi
    cookies = {c.name: c.value for c in cookie_jar}

    # Create session with Chrome impersonation to bypass Cloudflare
    session = requests.Session(impersonate="chrome")
    session.headers.update(API_HEADERS)
    session.cookies.update(cookies)

    return session


def _api_request(
    session: "requests.Session",
    url: str,
    retries: int = 3,
) -> dict | list:
    """Make API request with error handling and retries.

    Args:
        session: Authenticated requests session
        url: Full URL to request
        retries: Number of retry attempts for transient failures

    Returns:
        Parsed JSON response

    Raises:
        SessionExpiredError: If session is invalid/expired
        APIError: For other API failures
        FileNotFoundError: If resource not found (404)
    """
    import time

    last_error = None

    for attempt in range(retries):
        try:
            log.debug(f"GET {url} (attempt {attempt + 1}/{retries})")
            response = session.get(url, timeout=REQUEST_TIMEOUT)

            # Check for auth errors
            if response.status_code in (401, 403):
                raise SessionExpiredError(
                    "Session expired or invalid.\n"
                    "Please log into claude.ai in your browser and retry."
                )

            # Check for not found
            if response.status_code == 404:
                raise FileNotFoundError(f"Resource not found: {url}")

            # Check for rate limiting
            if response.status_code == 429:
                raise APIError(
                    "Rate limited by Claude.ai.\n"
                    "Wait a few minutes and try again."
                )

            # Check for server errors - RETRY these
            if response.status_code >= 500:
                if attempt < retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    status_hints = {
                        502: "Bad Gateway - Claude.ai may be updating",
                        503: "Service Unavailable - server overloaded",
                        504: "Gateway Timeout - request took too long",
                    }
                    hint = status_hints.get(response.status_code, "Server error")
                    log.warning(f"{hint} ({response.status_code}), retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue  # Retry the loop
                raise APIError(
                    f"Claude.ai server error ({response.status_code}) after {retries} attempts.\n"
                    "The service may be experiencing issues. Try again later."
                )

            # Check for other errors
            response.raise_for_status()

            # Validate content type
            content_type = response.headers.get('content-type', '')
            if 'application/json' not in content_type:
                body_preview = response.text[:500]
                if '<html' in body_preview.lower() or '<!doctype' in body_preview.lower():
                    raise APIError(
                        "API returned HTML instead of JSON.\n"
                        "This usually means Cloudflare blocked the request.\n"
                        "Try again in a few minutes, or verify claude.ai is accessible in your browser."
                    )
                raise APIError(f"Unexpected content-type: {content_type}")

            # Check for empty response
            if not response.text.strip():
                raise APIError("Empty response from API")

            # Parse JSON with better error handling
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                raise APIError(f"Invalid JSON in API response: {e}") from e

            # Add delay between requests to be nice
            time.sleep(REQUEST_DELAY)

            return data

        except (SessionExpiredError, FileNotFoundError, APIError):
            raise
        except (OSError, ConnectionError, TimeoutError) as e:
            error_str = str(e).lower()
            if "timeout" in error_str:
                last_error = APIError(
                    "Request timed out.\n"
                    "Check your internet connection and try again."
                )
            else:
                last_error = APIError(f"Connection error: {e}")
            if attempt < retries - 1:
                log.warning(f"Network error, retrying in 1s... ({e})")
                time.sleep(1)
        except Exception as e:
            raise APIError(f"Request failed: {e}") from e

    # All retries exhausted
    if last_error:
        raise last_error
    raise APIError("Request failed after all retries")


def discover_organizations(session: "requests.Session") -> list[dict]:
    """Discover available organizations via bootstrap endpoint.

    Args:
        session: Authenticated requests session

    Returns:
        List of organization dicts with uuid and name
    """
    url = "https://claude.ai/api/bootstrap"
    data = _api_request(session, url)

    if not isinstance(data, dict):
        raise APIError(f"Unexpected bootstrap response: {type(data)}")

    memberships = data.get("account", {}).get("memberships", [])
    orgs = []
    for m in memberships:
        org = m.get("organization", {})
        if org.get("uuid"):
            orgs.append({"uuid": org["uuid"], "name": org.get("name", "Unknown")})

    return orgs


def fetch_projects(session: "requests.Session", org_uuid: str) -> list[dict]:
    """Fetch all projects for an organization (list only, no prompt_template).

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID

    Returns:
        List of project dicts (basic metadata only)
    """
    url = f"{API_BASE}/{org_uuid}/projects"
    projects = _api_request(session, url)

    if not isinstance(projects, list):
        raise APIError(f"Unexpected response format: expected list, got {type(projects)}")

    log.debug(f"Fetched {len(projects)} projects")
    return projects


def fetch_project_details(
    session: "requests.Session", org_uuid: str, project_uuid: str
) -> dict:
    """Fetch full project details including prompt_template.

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID
        project_uuid: Project UUID

    Returns:
        Project dict with full metadata including prompt_template
    """
    url = f"{API_BASE}/{org_uuid}/projects/{project_uuid}"
    project = _api_request(session, url)

    if not isinstance(project, dict):
        raise APIError(f"Unexpected response format: expected dict, got {type(project)}")

    return project


def fetch_project_docs(
    session: "requests.Session", org_uuid: str, project_uuid: str
) -> list[dict]:
    """Fetch all documents for a project.

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID
        project_uuid: Project UUID

    Returns:
        List of document dicts with content
    """
    url = f"{API_BASE}/{org_uuid}/projects/{project_uuid}/docs"
    params = "?tree=true"
    docs = _api_request(session, url + params)

    if not isinstance(docs, list):
        raise APIError(f"Unexpected response format: expected list, got {type(docs)}")

    log.debug(f"Fetched {len(docs)} docs for project {project_uuid}")
    return docs


def fetch_project_conversations(
    session: "requests.Session", org_uuid: str, project_uuid: str
) -> list[dict]:
    """Fetch conversation list for a project.

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID
        project_uuid: Project UUID

    Returns:
        List of conversation metadata dicts
    """
    url = f"{API_BASE}/{org_uuid}/projects/{project_uuid}/conversations"
    params = "?tree=true"
    convos = _api_request(session, url + params)

    if not isinstance(convos, list):
        raise APIError(f"Unexpected response format: expected list, got {type(convos)}")

    log.debug(f"Fetched {len(convos)} conversations for project {project_uuid}")
    return convos


def fetch_conversation(
    session: "requests.Session", org_uuid: str, conversation_uuid: str
) -> dict:
    """Fetch full conversation with messages.

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID
        conversation_uuid: Conversation UUID

    Returns:
        Conversation dict with chat_messages
    """
    url = f"{API_BASE}/{org_uuid}/chat_conversations/{conversation_uuid}"
    params = "?rendering_mode=messages&render_all_tools=true"
    convo = _api_request(session, url + params)

    if not isinstance(convo, dict):
        raise APIError(f"Unexpected response format: expected dict, got {type(convo)}")

    return convo


# =============================================================================
# Filename Sanitization (Task 8co.6)
# =============================================================================

# Characters invalid on Windows and/or Unix
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserved device names
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ["COM", "LPT"] for i in range(1, 10)
}


def sanitize_filename(name: str, max_len: int = 200) -> str:
    """Convert string to valid cross-platform filename.

    Handles:
    - Invalid characters: <>:"/\\|?*
    - Windows reserved names (CON, PRN, etc.)
    - Leading/trailing spaces and dots
    - NULL bytes and control characters
    - Unicode normalization (NFC)
    - Length limits with hash suffix for long names

    Args:
        name: Original filename or title
        max_len: Maximum filename length (default 200, leaves room for extensions)

    Returns:
        Safe filename string, never empty
    """
    # Normalize unicode to NFC (consistent across platforms)
    name = unicodedata.normalize("NFC", name)

    # Replace invalid characters with hyphen
    name = INVALID_FILENAME_CHARS.sub("-", name)

    # Collapse multiple hyphens
    name = re.sub(r"-+", "-", name)

    # Strip leading/trailing spaces, dots, and hyphens
    name = name.strip(" .-")

    # Handle Windows reserved names
    stem = name.rsplit(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        name = f"_{name}"

    # Truncate with hash if too long
    if len(name) > max_len:
        hash_suffix = hashlib.md5(name.encode()).hexdigest()[:8]
        name = f"{name[:max_len - 10]}_{hash_suffix}"

    # Ensure non-empty
    return name or "unnamed"


def get_unique_filename(
    base: str, existing: set[str], case_insensitive: bool = True
) -> str:
    """Get unique filename avoiding collisions.

    Args:
        base: Base filename to make unique
        existing: Set of already-used filenames
        case_insensitive: If True, treat 'File.md' and 'file.md' as collision
                         (needed for macOS HFS+)

    Returns:
        Unique filename, possibly with numeric suffix
    """
    # Comparison function based on case sensitivity
    def normalize(s: str) -> str:
        return s.lower() if case_insensitive else s

    existing_normalized = {normalize(f) for f in existing}

    # Try base name first
    if normalize(base) not in existing_normalized:
        return base

    # Split extension
    if "." in base:
        stem, ext = base.rsplit(".", 1)
        ext = f".{ext}"
    else:
        stem, ext = base, ""

    # Try numbered variants
    for i in range(1, 1000):
        candidate = f"{stem}_{i}{ext}"
        if normalize(candidate) not in existing_normalized:
            return candidate

    # Extremely unlikely, but handle it
    hash_suffix = hashlib.md5(base.encode()).hexdigest()[:8]
    return f"{stem}_{hash_suffix}{ext}"


def make_project_slug(name: str, uuid: str) -> str:
    """Create project directory name from project name and UUID.

    Args:
        name: Project name
        uuid: Project UUID

    Returns:
        Directory name like 'project-name-abc12345'
    """
    # Sanitize and lowercase the name
    slug = sanitize_filename(name).lower()

    # Replace spaces with hyphens
    slug = re.sub(r"\s+", "-", slug)

    # Take first 8 chars of UUID for uniqueness
    short_uuid = uuid.replace("-", "")[:8]

    # Combine, limit total length
    if len(slug) > 50:
        slug = slug[:50].rstrip("-")

    return f"{slug}-{short_uuid}"


# =============================================================================
# Output Structure (Task 8co.7)
# =============================================================================


def write_project_output(
    project: dict,
    docs: list[dict],
    output_dir: Path,
) -> Path:
    """Write project data to output directory structure.

    Creates:
        <output_dir>/<project-slug>/
        ├── CLAUDE.md           # From prompt_template
        ├── meta.json           # Project metadata
        └── docs/               # Project documents

    Args:
        project: Project metadata dict
        docs: List of document dicts
        output_dir: Base output directory

    Returns:
        Path to created project directory
    """
    from datetime import datetime, timezone

    project_uuid = project["uuid"]
    project_name = project.get("name", "Unnamed Project")

    # Create project directory
    project_slug = make_project_slug(project_name, project_uuid)
    project_dir = output_dir / project_slug
    project_dir.mkdir(parents=True, exist_ok=True)

    # Check for UUID collision - another project might own this directory
    meta_path = project_dir / "meta.json"
    if meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text())
            existing_uuid = existing_meta.get("uuid")
            if existing_uuid and existing_uuid != project.get("uuid"):
                # Different project owns this directory! This is a collision.
                log.error(
                    f"SLUG COLLISION: Directory {project_dir.name} belongs to project "
                    f"{existing_uuid}, not {project.get('uuid')}. "
                    f"Please manually rename one of the directories."
                )
                raise ValueError(f"Slug collision detected for {project_dir.name}")
        except json.JSONDecodeError:
            log.warning(f"Corrupted meta.json in {project_dir}, will overwrite")

    # Write CLAUDE.md from prompt_template
    prompt_template = project.get("prompt_template", "")
    claude_md_path = project_dir / "CLAUDE.md"

    synced_at = datetime.now(timezone.utc).isoformat()

    if prompt_template:
        claude_md_content = f"""---
synced_at: {synced_at}
source: claude.ai/project/{project_uuid}
---

{prompt_template}
"""
    else:
        claude_md_content = f"""---
synced_at: {synced_at}
source: claude.ai/project/{project_uuid}
---

# {project_name}

_No project instructions defined._
"""

    claude_md_path.write_text(claude_md_content, encoding="utf-8")
    log.debug(f"Wrote {claude_md_path}")

    # Write meta.json with full project metadata
    meta = {
        "uuid": project_uuid,
        "name": project_name,
        "description": project.get("description", ""),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at"),
        "is_private": project.get("is_private", True),
        "synced_at": synced_at,
    }
    meta_path = project_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log.debug(f"Wrote {meta_path}")

    # Write docs
    if docs:
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(exist_ok=True)

        used_filenames: set[str] = set()
        for doc in docs:
            # API uses 'file_name' key
            doc_filename = doc.get("file_name") or doc.get("filename") or "untitled.md"
            # Ensure .md extension
            if not doc_filename.lower().endswith(".md"):
                doc_filename = f"{doc_filename}.md"

            # Sanitize and make unique
            safe_filename = sanitize_filename(doc_filename)
            unique_filename = get_unique_filename(safe_filename, used_filenames)
            used_filenames.add(unique_filename)

            # Write doc content
            doc_content = doc.get("content", "")
            doc_path = docs_dir / unique_filename
            doc_path.write_text(doc_content, encoding="utf-8")
            log.debug(f"Wrote {doc_path}")

    return project_dir


def write_index(
    projects: list[dict],
    output_dir: Path,
    org_uuid: str,
    synced_at: str,
    orphaned_projects: list[dict] | None = None,
) -> None:
    """Write index.json manifest file.

    Args:
        projects: List of project dicts (with 'docs_count' added)
        output_dir: Base output directory
        org_uuid: Organization UUID
        synced_at: ISO timestamp of sync
        orphaned_projects: List of projects deleted remotely but kept locally
    """
    index = {
        "synced_at": synced_at,
        "org_id": org_uuid,
        "projects": {},
    }

    for project in projects:
        project_uuid = project["uuid"]
        project_name = project.get("name", "Unnamed Project")
        project_slug = make_project_slug(project_name, project_uuid)

        index["projects"][project_uuid] = {
            "name": project_name,
            "slug": project_slug,
            "path": f"{project_slug}/",
            "updated_at": project.get("updated_at"),
            "docs_count": project.get("_docs_count", 0),
        }

    # Add orphaned projects (deleted remotely, kept locally)
    if orphaned_projects:
        for orphan in orphaned_projects:
            orphan_uuid = orphan["uuid"]
            orphan_name = orphan.get("name", "Unknown")
            orphan_slug = make_project_slug(orphan_name, orphan_uuid)

            index["projects"][orphan_uuid] = {
                "name": orphan_name,
                "slug": orphan_slug,
                "path": f"{orphan_slug}/",
                "orphaned": True,
                "orphaned_at": orphan.get("_orphaned_at"),
            }

    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.info(f"Wrote {index_path}")


# =============================================================================
# Sync State Management (Incremental Sync)
# =============================================================================

SYNC_STATE_FILE = ".sync-state.json"


def compute_doc_hash(content: str) -> str:
    """Compute hash of document content for change detection.

    Normalizes content before hashing to avoid false positives from:
    - Unicode normalization differences (NFD vs NFC)
    - Line ending differences (CRLF vs LF vs CR)

    Note: Hash algorithm changed in v1.x to include normalization.
    First sync after upgrade will re-sync all content (expected).
    """
    # Normalize unicode to NFC (composed form)
    normalized = unicodedata.normalize("NFC", content)

    # Normalize line endings to LF
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def load_sync_state(output_dir: Path) -> dict:
    """Load previous sync state from output directory.

    Returns:
        Dict with structure:
        {
            "synced_at": "ISO timestamp",
            "projects": {
                "<uuid>": {
                    "updated_at": "API timestamp",
                    "docs": {
                        "<doc_uuid>": {"hash": "...", "filename": "..."}
                    }
                }
            }
        }
    """
    state_path = output_dir / SYNC_STATE_FILE
    if not state_path.exists():
        return {"projects": {}}

    try:
        with open(state_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.warning(f"Could not load sync state: {e}")
        return {"projects": {}}


def save_sync_state(output_dir: Path, state: dict) -> None:
    """Save sync state to output directory."""
    state_path = output_dir / SYNC_STATE_FILE
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)
    log.debug(f"Saved sync state to {state_path}")


def project_needs_sync(
    project: dict, docs: list[dict], prev_state: dict
) -> tuple[bool, str]:
    """Check if project needs to be synced.

    Args:
        project: Current project metadata from API
        docs: Current docs from API
        prev_state: Previous sync state

    Returns:
        Tuple of (needs_sync: bool, reason: str)
    """
    project_uuid = project["uuid"]
    prev_project = prev_state.get("projects", {}).get(project_uuid)

    if not prev_project:
        return True, "new project"

    # Check project updated_at timestamp
    current_updated = project.get("updated_at", "")
    prev_updated = prev_project.get("updated_at", "")

    if current_updated != prev_updated:
        return True, f"updated ({prev_updated[:10]} → {current_updated[:10]})"

    # Check prompt_template (instructions) changed
    current_template_hash = compute_doc_hash(project.get("prompt_template", ""))
    prev_template_hash = prev_project.get("prompt_template_hash", "")
    if current_template_hash != prev_template_hash:
        return True, "instructions changed"

    # Check doc count changed
    prev_doc_count = len(prev_project.get("docs", {}))
    if len(docs) != prev_doc_count:
        return True, f"doc count changed ({prev_doc_count} → {len(docs)})"

    # Check doc content hashes
    prev_docs = prev_project.get("docs", {})
    for doc in docs:
        doc_uuid = doc.get("uuid", "")
        content = doc.get("content", "")
        current_hash = compute_doc_hash(content)

        prev_doc = prev_docs.get(doc_uuid, {})
        if prev_doc.get("hash") != current_hash:
            return True, f"doc content changed"

    return False, "unchanged"


def detect_deleted_projects(prev_state: dict, current_projects: list[dict]) -> list[str]:
    """Detect projects that were deleted remotely.

    Args:
        prev_state: Previous sync state
        current_projects: Current projects from API

    Returns:
        List of deleted project UUIDs
    """
    current_uuids = {p["uuid"] for p in current_projects}
    prev_uuids = set(prev_state.get("projects", {}).keys())
    return list(prev_uuids - current_uuids)


def build_project_state(project: dict, docs: list[dict]) -> dict:
    """Build sync state entry for a project."""
    doc_states = {}
    for doc in docs:
        doc_uuid = doc.get("uuid", "")
        if doc_uuid:
            doc_states[doc_uuid] = {
                "hash": compute_doc_hash(doc.get("content", "")),
                "filename": doc.get("file_name") or doc.get("filename", ""),
            }

    state = {
        "name": project.get("name", "Unknown"),
        "updated_at": project.get("updated_at", ""),
        "prompt_template_hash": compute_doc_hash(project.get("prompt_template", "")),
        "docs": doc_states,
    }

    # Include conversation state if present
    if "_conversations" in project:
        state["conversations"] = project["_conversations"]

    return state


# =============================================================================
# Conversation Output (Task 8co.11)
# =============================================================================


def conversation_needs_sync(
    convo_meta: dict, prev_convos: dict, force_full: bool = False
) -> tuple[bool, str]:
    """Check if a conversation needs to be synced.

    Args:
        convo_meta: Conversation metadata from API (has updated_at)
        prev_convos: Previous conversation state dict
        force_full: Force sync even if unchanged

    Returns:
        Tuple of (needs_sync: bool, reason: str)
    """
    if force_full:
        return True, "full sync"

    convo_uuid = convo_meta.get("uuid", "")
    prev_convo = prev_convos.get(convo_uuid)

    if not prev_convo:
        return True, "new"

    current_updated = convo_meta.get("updated_at", "")
    prev_updated = prev_convo.get("updated_at", "")

    if current_updated != prev_updated:
        return True, "updated"

    return False, "unchanged"


def write_conversation_index(project_dir: Path, convo_index: dict, synced_at: str) -> None:
    """Write conversations/index.json manifest.

    Args:
        project_dir: Project directory path
        convo_index: Dict mapping convo UUID to metadata
        synced_at: ISO timestamp of sync
    """
    convos_dir = project_dir / "conversations"
    convos_dir.mkdir(exist_ok=True)

    index = {
        "synced_at": synced_at,
        "conversations": convo_index,
    }

    index_path = convos_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.debug(f"Wrote {index_path}")


def write_conversation_output(
    conversation: dict,
    project_dir: Path,
    used_filenames: set[str],
) -> str | None:
    """Write conversation to project's conversations directory.

    Creates:
        <project_dir>/conversations/<name>.md

    Args:
        conversation: Full conversation dict with chat_messages
        project_dir: Project directory path
        used_filenames: Set of already-used filenames (updated in place)

    Returns:
        Filename used, or None if no messages
    """
    from datetime import datetime, timezone

    messages = conversation.get("chat_messages", [])
    if not messages:
        return None

    convo_name = conversation.get("name", "Untitled")
    convo_uuid = conversation.get("uuid", "unknown")
    created_at = conversation.get("created_at", "")
    updated_at = conversation.get("updated_at", "")

    # Create conversations directory
    convos_dir = project_dir / "conversations"
    convos_dir.mkdir(exist_ok=True)

    # Generate filename from conversation name
    base_filename = sanitize_filename(convo_name)
    if not base_filename.lower().endswith(".md"):
        base_filename = f"{base_filename}.md"

    filename = get_unique_filename(base_filename, used_filenames)
    used_filenames.add(filename)

    # Build markdown content
    lines = [
        "---",
        f"conversation_id: {convo_uuid}",
        f"name: {convo_name}",
        f"created_at: {created_at}",
        f"updated_at: {updated_at}",
        f"message_count: {len(messages)}",
        f"synced_at: {datetime.now(timezone.utc).isoformat()}",
        "---",
        "",
        f"# {convo_name}",
        "",
    ]

    for msg in messages:
        sender = msg.get("sender", "unknown")
        msg_created = msg.get("created_at", "")

        # Extract message content from content array (API returns content as array of blocks)
        # Each block has 'type' ('text', 'thinking', etc.) and the content in a matching key
        content_parts = []
        content_blocks = msg.get("content", [])
        if isinstance(content_blocks, list):
            for block in content_blocks:
                if isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type == "text":
                        content_parts.append(block.get("text", ""))
                    elif block_type == "thinking":
                        # Include thinking blocks in collapsed format
                        thinking_text = block.get("thinking", "")
                        if thinking_text:
                            content_parts.append(f"<details>\n<summary>Thinking...</summary>\n\n{thinking_text}\n</details>")
        content = "\n\n".join(filter(None, content_parts))

        # Fallback to legacy 'text' field if content array is empty
        if not content:
            content = msg.get("text", "")

        # Format sender nicely
        if sender == "human":
            sender_label = "**Human**"
        elif sender == "assistant":
            sender_label = "**Claude**"
        else:
            sender_label = f"**{sender}**"

        # Add timestamp if available
        if msg_created:
            try:
                # Parse and format timestamp
                dt = datetime.fromisoformat(msg_created.replace("Z", "+00:00"))
                timestamp = dt.strftime("%Y-%m-%d %H:%M")
                sender_label = f"{sender_label} ({timestamp})"
            except (ValueError, AttributeError):
                pass

        lines.append(f"## {sender_label}")
        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    # Write file
    convo_path = convos_dir / filename
    convo_path.write_text("\n".join(lines), encoding="utf-8")
    log.debug(f"Wrote conversation: {convo_path}")

    return filename


# =============================================================================
# Git Auto-Commit (Task 3ha)
# =============================================================================


def git_auto_commit(output_dir: Path, message: str | None = None) -> bool:
    """Initialize git repo if needed and commit all changes.

    Args:
        output_dir: Output directory to commit
        message: Commit message (default: "Sync <timestamp>")

    Returns:
        True if committed, False if nothing to commit or error
    """
    import subprocess
    from datetime import datetime, timezone

    git_dir = output_dir / ".git"

    try:
        # Initialize if not already a repo
        if not git_dir.exists():
            log.info("Initializing git repository...")
            subprocess.run(
                ["git", "init"],
                cwd=output_dir,
                capture_output=True,
                check=True,
            )

        # Check if there are changes
        status_result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=output_dir,
            capture_output=True,
            text=True,
        )

        if not status_result.stdout.strip():
            log.info("No changes to commit")
            return False

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            cwd=output_dir,
            capture_output=True,
            check=True,
        )

        # Commit
        if not message:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            message = f"Sync {timestamp}"

        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=output_dir,
            capture_output=True,
            check=True,
        )

        log.info(f"Committed changes: {message}")
        return True

    except subprocess.CalledProcessError as e:
        log.warning(f"Git operation failed: {e.stderr.decode() if e.stderr else e}")
        return False
    except FileNotFoundError:
        log.warning("Git not found in PATH, skipping auto-commit")
        return False


# =============================================================================
# Main Entry Point
# =============================================================================


def sync(config: Config) -> int:
    """Execute sync operation.

    Args:
        config: Runtime configuration

    Returns:
        Exit code (0 for success)
    """
    from datetime import datetime, timezone

    from tqdm import tqdm

    # Set up signal handlers for graceful interruption
    import signal
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    global _interrupted
    _interrupted = False  # Reset for this sync run

    # org_uuid is guaranteed to be set by main() at this point
    assert config.org_uuid is not None
    org_uuid = config.org_uuid

    log.info(f"Syncing organization {org_uuid}")
    log.info(f"Output directory: {config.output_dir}")
    log.info(f"Browser: {config.browser}")
    if not config.skip_conversations:
        log.info("Including conversations (use --skip-conversations to disable)")
    if config.full_sync:
        log.info("Full sync mode (ignoring cached state)")

    synced_at = datetime.now(timezone.utc).isoformat()

    try:
        # Step 1: Get session cookies
        log.info("Extracting session cookies...")
        cookies = get_session_cookies(config.browser)

        # Step 2: Create authenticated session
        session = create_session(cookies)

        # Step 3: Fetch projects
        log.info("Fetching projects...")
        projects = fetch_projects(session, org_uuid)
        log.info(f"Found {len(projects)} projects")

        # Step 3b: Filter to single project if requested
        if config.project_filter:
            filter_str = config.project_filter.lower()
            filtered = [
                p for p in projects
                if filter_str in p["uuid"].lower() or filter_str in p.get("name", "").lower()
            ]
            if not filtered:
                log.error(f"No project matches filter '{config.project_filter}'")
                log.info("Available projects:")
                for p in projects:
                    log.info(f"  {p['uuid'][:8]}  {p.get('name', 'Unknown')}")
                return 1
            if len(filtered) > 1:
                log.warning(f"Filter '{config.project_filter}' matched {len(filtered)} projects:")
                for p in filtered:
                    log.warning(f"  {p['uuid'][:8]}  {p.get('name', 'Unknown')}")
            projects = filtered
            log.info(f"Filtered to {len(projects)} project(s)")

        # Step 4: Load previous sync state (for incremental sync)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        prev_state = {} if config.full_sync else load_sync_state(config.output_dir)
        new_state = {"synced_at": synced_at, "projects": {}}

        # Step 5: Process each project
        synced_projects = []
        synced_count = 0
        skipped_count = 0

        for project in tqdm(projects, desc="Syncing projects", unit="project"):
            if _interrupted:
                log.info("Stopping sync early due to interrupt")
                break

            project_uuid = project["uuid"]
            project_name = project.get("name", "Unknown")
            log.debug(f"Processing: {project_name}")

            # Fetch full project details (includes prompt_template)
            full_project = fetch_project_details(session, org_uuid, project_uuid)

            # Fetch docs
            docs = fetch_project_docs(session, org_uuid, project_uuid)
            full_project["_docs_count"] = len(docs)

            # Check if sync needed (incremental)
            needs_sync, reason = project_needs_sync(full_project, docs, prev_state)

            if needs_sync or config.full_sync:
                log.debug(f"Syncing {project_name}: {reason}")
                project_dir = write_project_output(full_project, docs, config.output_dir)

                # Sync conversations (default on, skip with --skip-conversations)
                if not config.skip_conversations:
                    convo_list = fetch_project_conversations(session, org_uuid, project_uuid)
                    if convo_list:
                        # Get previous conversation state for incremental sync
                        prev_project_state = prev_state.get("projects", {}).get(project_uuid, {})
                        prev_convos = prev_project_state.get("conversations", {})

                        convos_synced = 0
                        convos_skipped = 0
                        used_convo_filenames: set[str] = set()
                        convo_index: dict[str, dict] = {}

                        for convo_meta in convo_list:
                            convo_uuid = convo_meta.get("uuid")
                            if not convo_uuid:
                                continue

                            # Check if conversation needs sync (incremental)
                            convo_needs_sync, convo_reason = conversation_needs_sync(
                                convo_meta, prev_convos, config.full_sync
                            )

                            if convo_needs_sync:
                                try:
                                    full_convo = fetch_conversation(session, org_uuid, convo_uuid)
                                    filename = write_conversation_output(
                                        full_convo, project_dir, used_convo_filenames
                                    )
                                    if filename:
                                        convo_index[convo_uuid] = {
                                            "name": convo_meta.get("name", "Untitled"),
                                            "filename": filename,
                                            "created_at": convo_meta.get("created_at"),
                                            "updated_at": convo_meta.get("updated_at"),
                                            "message_count": len(full_convo.get("chat_messages", [])),
                                        }
                                        convos_synced += 1
                                except (APIError, FileNotFoundError) as e:
                                    log.warning(f"Failed to fetch conversation {convo_uuid}: {e}")
                            else:
                                # Keep previous index entry for unchanged conversations
                                if convo_uuid in prev_convos:
                                    convo_index[convo_uuid] = prev_convos[convo_uuid]
                                convos_skipped += 1

                        # Write conversation index
                        if convo_index:
                            write_conversation_index(project_dir, convo_index, synced_at)

                        if convos_skipped > 0:
                            log.debug(f"Conversations: {convos_synced} synced, {convos_skipped} skipped")
                        elif convos_synced > 0:
                            log.debug(f"Conversations: {convos_synced} synced")

                        # Store conversation state for next sync
                        full_project["_conversations"] = convo_index

                synced_count += 1
            else:
                log.debug(f"Skipping {project_name}: {reason}")
                skipped_count += 1

            # Build state for this project (always update state)
            new_state["projects"][project_uuid] = build_project_state(full_project, docs)
            synced_projects.append(full_project)

        # Step 6: Detect deleted projects and mark as orphaned
        deleted_uuids = detect_deleted_projects(prev_state, projects)
        orphaned_projects = []
        for deleted_uuid in deleted_uuids:
            prev_project = prev_state.get("projects", {}).get(deleted_uuid, {})
            # Keep the project info but mark as orphaned
            orphaned_projects.append({
                "uuid": deleted_uuid,
                "name": prev_project.get("name", "Unknown"),
                "_orphaned": True,
                "_orphaned_at": synced_at,
            })
            log.warning(f"Project '{prev_project.get('name', deleted_uuid)}' deleted remotely (local files kept)")

        # Step 7: Write index and save sync state
        write_index(synced_projects, config.output_dir, org_uuid, synced_at, orphaned_projects)
        save_sync_state(config.output_dir, new_state)

        # Step 7: Git auto-commit
        if config.auto_commit:
            git_auto_commit(config.output_dir)

        # Summary
        if skipped_count > 0:
            log.info(f"Sync complete! {synced_count} updated, {skipped_count} unchanged")
        else:
            log.info(f"Sync complete! {len(projects)} projects synced to {config.output_dir}")

        return 0

    except CookieExtractionError as e:
        log.error(f"Cookie extraction failed:\n{e}")
        return 1
    except SessionExpiredError as e:
        log.error(f"Session error:\n{e}")
        return 1
    except APIError as e:
        log.error(f"API error:\n{e}")
        return 1
    except NotImplementedError as e:
        log.error(f"Feature not implemented: {e}")
        return 1
    except Exception as e:
        log.error(f"Sync failed: {e}")
        if config.verbose:
            import traceback

            tb = traceback.format_exc()
            log.error(sanitize_sensitive_data(tb))
        return 1


def parse_args(argv: list[str] | None = None) -> Config:
    """Parse command line arguments.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Config object with parsed settings
    """
    # Load defaults from environment
    env_config = get_config_from_env()

    parser = argparse.ArgumentParser(
        description="Sync Claude web app projects to local storage for Claude Code.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Auto-discover org (if only one)
  %(prog)s --list-orgs                        # List available organizations
  %(prog)s f3e5048f-1380-4436-83cf-085832fff594
  %(prog)s f3e5048f-1380-4436-83cf-085832fff594 -o ./my-projects

Finding your org UUID:
  Run with --list-orgs to see available organizations, or:
  1. Open claude.ai, log in
  2. DevTools (F12) > Network tab
  3. Filter for 'organizations' in any request URL

Environment:
  CLAUDE_ORG_UUID    Default organization UUID
  .claude-sync.env   Local config file (checked in cwd and ~/)
        """,
    )

    parser.add_argument(
        "org_uuid",
        nargs="?",
        default=env_config.get("CLAUDE_ORG_UUID"),
        help="Organization UUID (optional if only one org, or set CLAUDE_ORG_UUID)",
    )

    parser.add_argument(
        "--list-orgs",
        action="store_true",
        help="List available organizations and exit",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )

    parser.add_argument(
        "-b",
        "--browser",
        choices=SUPPORTED_BROWSERS,
        default="edge",
        help="Browser to extract cookies from (default: edge)",
    )

    parser.add_argument(
        "--skip-conversations",
        action="store_true",
        help="Skip syncing project conversations (faster sync)",
    )

    parser.add_argument(
        "-p",
        "--project",
        type=str,
        default=None,
        help="Sync only this project (UUID or name substring match)",
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Force full sync, ignore cached state",
    )

    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Disable automatic git init and commit",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args(argv)

    # org_uuid validation happens in main() after checking list_orgs

    return Config(
        org_uuid=args.org_uuid,
        output_dir=args.output,
        browser=args.browser,
        skip_conversations=args.skip_conversations,
        verbose=args.verbose,
        list_orgs=args.list_orgs,
        full_sync=args.full,
        auto_commit=not args.no_git,
        project_filter=args.project,
    )


def list_organizations(config: Config) -> int:
    """List available organizations and exit.

    Args:
        config: Runtime configuration

    Returns:
        Exit code
    """
    try:
        log.info("Extracting session cookies...")
        cookies = get_session_cookies(config.browser)
        session = create_session(cookies)

        log.info("Discovering organizations...")
        orgs = discover_organizations(session)

        if not orgs:
            log.error("No organizations found. Are you logged into claude.ai?")
            return 1

        print("\nAvailable organizations:")
        for org in orgs:
            print(f"  {org['uuid']}  {org['name']}")
        print(f"\nUse: ./claude_sync.py <uuid> to sync a specific organization")

        return 0

    except CookieExtractionError as e:
        log.error(f"Cookie extraction failed:\n{e}")
        return 1
    except APIError as e:
        log.error(f"API error:\n{e}")
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point.

    Args:
        argv: Command line arguments (defaults to sys.argv[1:])

    Returns:
        Exit code
    """
    config = parse_args(argv)

    if config.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Handle --list-orgs
    if config.list_orgs:
        return list_organizations(config)

    # Auto-discover org if not provided
    if not config.org_uuid:
        try:
            log.info("No org UUID provided, attempting auto-discovery...")
            cookies = get_session_cookies(config.browser)
            session = create_session(cookies)
            orgs = discover_organizations(session)

            if len(orgs) == 0:
                log.error("No organizations found. Are you logged into claude.ai?")
                return 1
            elif len(orgs) == 1:
                config.org_uuid = orgs[0]["uuid"]
                log.info(f"Auto-selected organization: {orgs[0]['name']}")
            else:
                log.error("Multiple organizations found. Please specify one:")
                for org in orgs:
                    print(f"  {org['uuid']}  {org['name']}")
                print("\nOr set CLAUDE_ORG_UUID in .claude-sync.env")
                return 1
        except CookieExtractionError as e:
            log.error(f"Cookie extraction failed:\n{e}")
            return 1
        except APIError as e:
            log.error(f"API error during discovery:\n{e}")
            return 1

    try:
        return sync(config)
    except KeyboardInterrupt:
        log.warning("\nSync interrupted")
        return 130  # Standard SIGINT exit code


if __name__ == "__main__":
    sys.exit(main())
