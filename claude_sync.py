#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["requests<3", "tqdm", "browser-cookie3"]
# ///
"""
claude-sync: Sync Claude web app projects to local storage.

Fetches projects, docs, and optionally conversations from claude.ai
and organizes them into a local directory structure for Claude Code integration.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import requests

# Constants
DEFAULT_OUTPUT_DIR = Path.home() / ".claude" / "synced-projects"
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


def get_session_cookies(browser: str) -> dict[str, str]:
    """Extract session cookies from browser.

    Args:
        browser: Browser to extract from ('edge' or 'chrome')

    Returns:
        Dict with 'sessionKey' and optionally 'cf_clearance'

    Raises:
        RuntimeError: If cookie extraction fails
    """
    # TODO: Implement in task 8co.4
    raise NotImplementedError("Cookie extraction not yet implemented")


# =============================================================================
# API Client (Task 8co.5)
# =============================================================================


def create_session(cookies: dict[str, str]) -> "requests.Session":
    """Create authenticated requests session.

    Args:
        cookies: Dict containing session cookies

    Returns:
        Configured requests.Session
    """
    # TODO: Implement in task 8co.5
    raise NotImplementedError("API client not yet implemented")


def fetch_projects(session: "requests.Session", org_uuid: str) -> list[dict]:
    """Fetch all projects for an organization.

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID

    Returns:
        List of project dicts
    """
    # TODO: Implement in task 8co.5
    raise NotImplementedError("API client not yet implemented")


def fetch_project_docs(
    session: "requests.Session", org_uuid: str, project_uuid: str
) -> list[dict]:
    """Fetch all documents for a project.

    Args:
        session: Authenticated requests session
        org_uuid: Organization UUID
        project_uuid: Project UUID

    Returns:
        List of document dicts
    """
    # TODO: Implement in task 8co.5
    raise NotImplementedError("API client not yet implemented")


# =============================================================================
# Filename Sanitization (Task 8co.6)
# =============================================================================


def sanitize_filename(name: str) -> str:
    """Convert string to valid cross-platform filename.

    Handles:
    - Invalid characters: <>:"/\\|?*
    - Windows reserved names (CON, PRN, etc.)
    - Leading/trailing spaces and dots
    - NULL bytes

    Args:
        name: Original filename or title

    Returns:
        Safe filename string
    """
    # TODO: Implement in task 8co.6
    raise NotImplementedError("Filename sanitization not yet implemented")


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
    # TODO: Implement in task 8co.7
    raise NotImplementedError("Output structure not yet implemented")


def write_index(projects: list[dict], output_dir: Path) -> None:
    """Write index.json manifest file.

    Args:
        projects: List of synced project metadata
        output_dir: Base output directory
    """
    # TODO: Implement in task 8co.7
    raise NotImplementedError("Output structure not yet implemented")


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
    log.info(f"Syncing organization {config.org_uuid}")
    log.info(f"Output directory: {config.output_dir}")
    log.info(f"Browser: {config.browser}")

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

        for project in projects:
            log.info(f"Processing: {project.get('name', 'Unknown')}")
            docs = fetch_project_docs(session, config.org_uuid, project["uuid"])
            write_project_output(project, docs, config.output_dir)

        # Step 5: Write index
        write_index(projects, config.output_dir)

        log.info("Sync complete!")
        return 0

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
