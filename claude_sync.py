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


@dataclass
class Config:
    """Runtime configuration for sync operation."""

    org_uuid: str
    output_dir: Path
    browser: str
    include_conversations: bool = False
    verbose: bool = False


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
            f"Original error: {e}"
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
            f"Failed to extract cookies from {browser}: {e}"
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

            # Check for server errors
            if response.status_code >= 500:
                raise APIError(
                    f"Claude.ai server error ({response.status_code}).\n"
                    "Try again later."
                )

            # Check for other errors
            response.raise_for_status()

            # Add delay between requests to be nice
            time.sleep(REQUEST_DELAY)

            return response.json()

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
    projects: list[dict], output_dir: Path, org_uuid: str, synced_at: str
) -> None:
    """Write index.json manifest file.

    Args:
        projects: List of project dicts (with 'docs_count' added)
        output_dir: Base output directory
        org_uuid: Organization UUID
        synced_at: ISO timestamp of sync
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

    index_path = output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    log.info(f"Wrote {index_path}")


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

    log.info(f"Syncing organization {config.org_uuid}")
    log.info(f"Output directory: {config.output_dir}")
    log.info(f"Browser: {config.browser}")

    synced_at = datetime.now(timezone.utc).isoformat()

    try:
        # Step 1: Get session cookies
        log.info("Extracting session cookies...")
        cookies = get_session_cookies(config.browser)

        # Step 2: Create authenticated session
        session = create_session(cookies)

        # Step 3: Fetch projects
        log.info("Fetching projects...")
        projects = fetch_projects(session, config.org_uuid)
        log.info(f"Found {len(projects)} projects")

        # Step 4: Fetch docs and write output for each project
        config.output_dir.mkdir(parents=True, exist_ok=True)

        synced_projects = []
        for project in tqdm(projects, desc="Syncing projects", unit="project"):
            project_name = project.get("name", "Unknown")
            log.debug(f"Processing: {project_name}")

            # Fetch full project details (includes prompt_template)
            full_project = fetch_project_details(
                session, config.org_uuid, project["uuid"]
            )

            # Fetch docs
            docs = fetch_project_docs(session, config.org_uuid, project["uuid"])
            full_project["_docs_count"] = len(docs)  # Track for index

            write_project_output(full_project, docs, config.output_dir)
            synced_projects.append(full_project)

        # Step 5: Write index
        write_index(synced_projects, config.output_dir, config.org_uuid, synced_at)

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

            traceback.print_exc()
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
        description="Sync Claude web app projects to local storage.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s f3e5048f-1380-4436-83cf-085832fff594
  %(prog)s f3e5048f-1380-4436-83cf-085832fff594 -o ./my-projects
  %(prog)s f3e5048f-1380-4436-83cf-085832fff594 --browser chrome

Environment variables:
  CLAUDE_ORG_UUID    Default organization UUID
        """,
    )

    parser.add_argument(
        "org_uuid",
        nargs="?",
        default=env_config.get("CLAUDE_ORG_UUID"),
        help="Organization UUID (or set CLAUDE_ORG_UUID env var)",
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
        "-c",
        "--conversations",
        action="store_true",
        help="Also sync project conversations",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args(argv)

    # Validate org_uuid
    if not args.org_uuid:
        parser.error(
            "org_uuid is required. Provide as argument or set CLAUDE_ORG_UUID env var."
        )

    return Config(
        org_uuid=args.org_uuid,
        output_dir=args.output,
        browser=args.browser,
        include_conversations=args.conversations,
        verbose=args.verbose,
    )


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

    return sync(config)


if __name__ == "__main__":
    sys.exit(main())
