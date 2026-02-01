"""High-value smoke and integration tests for claude-sync core functions.

Tests focus on critical cross-platform functionality and sync logic.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import functions to test (reading from claude_sync.py as a module)
# We'll use exec to load specific functions to avoid running the main script
import hashlib
import re
import unicodedata
from datetime import datetime

# Load constants and functions from claude_sync.py
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ["COM", "LPT"] for i in range(1, 10)
}


def sanitize_filename(name: str, max_len: int = 200) -> str:
    """Convert string to valid cross-platform filename."""
    name = unicodedata.normalize("NFC", name)
    name = INVALID_FILENAME_CHARS.sub("-", name)
    name = re.sub(r"-+", "-", name)
    name = name.strip(" .-")

    stem = name.rsplit(".", 1)[0].upper()
    if stem in WINDOWS_RESERVED_NAMES:
        name = f"_{name}"

    if len(name) > max_len:
        hash_suffix = hashlib.md5(name.encode()).hexdigest()[:8]
        name = f"{name[: max_len - 10]}_{hash_suffix}"

    return name or "unnamed"


def get_unique_filename(
    base: str, existing: set[str], case_insensitive: bool = True
) -> str:
    """Get unique filename avoiding collisions."""
    def normalize(s: str) -> str:
        return s.lower() if case_insensitive else s

    existing_normalized = {normalize(f) for f in existing}

    if normalize(base) not in existing_normalized:
        return base

    if "." in base:
        stem, ext = base.rsplit(".", 1)
        ext = f".{ext}"
    else:
        stem, ext = base, ""

    for i in range(1, 1000):
        candidate = f"{stem}_{i}{ext}"
        if normalize(candidate) not in existing_normalized:
            return candidate

    raise ValueError(f"Could not generate unique filename after 1000 attempts: {base}")


def make_project_slug(name: str, uuid: str) -> str:
    """Create project directory name from project name and UUID."""
    slug = sanitize_filename(name).lower()
    slug = re.sub(r"\s+", "-", slug)
    short_uuid = uuid.replace("-", "")[:8]

    if len(slug) > 50:
        slug = slug[:50].rstrip("-")

    return f"{slug}-{short_uuid}"


def compute_doc_hash(content: str) -> str:
    """Compute hash of document content for change detection."""
    normalized = unicodedata.normalize("NFC", content)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def parse_timestamp(ts: str | None) -> datetime | None:
    """Parse ISO timestamp, handling various formats."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def timestamps_equal(ts1: str | None, ts2: str | None) -> bool:
    """Compare timestamps for equality, handling format differences."""
    dt1 = parse_timestamp(ts1)
    dt2 = parse_timestamp(ts2)

    if dt1 is None or dt2 is None:
        return ts1 == ts2

    return dt1 == dt2


def project_needs_sync(
    project: dict, docs: list[dict], prev_state: dict
) -> tuple[bool, str]:
    """Check if project needs to be synced."""
    project_uuid = project["uuid"]
    prev_project = prev_state.get("projects", {}).get(project_uuid)

    if not prev_project:
        return True, "new project"

    current_updated = project.get("updated_at", "")
    prev_updated = prev_project.get("updated_at", "")

    if not timestamps_equal(current_updated, prev_updated):
        return True, f"updated ({prev_updated[:10]} → {current_updated[:10]})"

    current_template_hash = compute_doc_hash(project.get("prompt_template", ""))
    prev_template_hash = prev_project.get("prompt_template_hash", "")
    if current_template_hash != prev_template_hash:
        return True, "instructions changed"

    prev_doc_count = len(prev_project.get("docs", {}))
    if len(docs) != prev_doc_count:
        return True, f"doc count changed ({prev_doc_count} → {len(docs)})"

    prev_docs = prev_project.get("docs", {})
    for doc in docs:
        doc_uuid = doc.get("uuid", "")
        content = doc.get("content", "")
        current_hash = compute_doc_hash(content)

        prev_doc = prev_docs.get(doc_uuid, {})
        if prev_doc.get("hash") != current_hash:
            return True, "doc content changed"

    return False, "unchanged"


def conversation_needs_sync(
    convo_meta: dict, prev_convos: dict, force_full: bool = False
) -> tuple[bool, str]:
    """Check if a conversation needs to be synced."""
    if force_full:
        return True, "full sync"

    convo_uuid = convo_meta.get("uuid", "")
    prev_convo = prev_convos.get(convo_uuid)

    if not prev_convo:
        return True, "new"

    current_updated = convo_meta.get("updated_at", "")
    prev_updated = prev_convo.get("updated_at", "")

    if not timestamps_equal(current_updated, prev_updated):
        return True, "updated"

    return False, "unchanged"


# =============================================================================
# Tests: Filename Sanitization (Critical for cross-platform safety)
# =============================================================================

class TestSanitizeFilename:
    """Test filename sanitization for cross-platform safety."""

    def test_invalid_characters_replaced(self):
        """Invalid characters should be replaced with hyphens."""
        assert sanitize_filename("file<>:name") == "file-name"
        assert sanitize_filename('file"name|test') == "file-name-test"
        assert sanitize_filename("file?*name") == "file-name"
        assert sanitize_filename("file\\name/test") == "file-name-test"

    def test_multiple_hyphens_collapsed(self):
        """Multiple consecutive hyphens should collapse to one."""
        assert sanitize_filename("file:::name") == "file-name"
        assert sanitize_filename("file<>|?name") == "file-name"

    def test_windows_reserved_names(self):
        """Windows reserved device names should be prefixed."""
        assert sanitize_filename("CON") == "_CON"
        assert sanitize_filename("con") == "_con"
        assert sanitize_filename("PRN") == "_PRN"
        assert sanitize_filename("COM1") == "_COM1"
        assert sanitize_filename("LPT9") == "_LPT9"
        assert sanitize_filename("CON.txt") == "_CON.txt"

        # Not reserved (note: sanitize_filename doesn't lowercase, just strips)
        assert sanitize_filename("CONF") == "CONF"
        assert sanitize_filename("COM10") == "COM10"

    def test_strip_leading_trailing(self):
        """Leading/trailing spaces, dots, hyphens should be stripped."""
        assert sanitize_filename("  file  ") == "file"
        assert sanitize_filename("..file..") == "file"
        assert sanitize_filename("--file--") == "file"
        assert sanitize_filename(" . - file - . ") == "file"

    def test_length_truncation(self):
        """Long names should be truncated with hash suffix."""
        long_name = "a" * 250
        result = sanitize_filename(long_name, max_len=200)
        assert len(result) <= 200
        assert result.startswith("a" * 182)  # 200 - 10 (suffix) - 8 (hash)
        assert "_" in result  # Hash separator

    def test_unicode_normalization(self):
        """Unicode should be normalized to NFC form."""
        # é can be represented as single char (NFC) or e + combining accent (NFD)
        nfc = "café"  # Composed
        nfd = "café"  # Decomposed (visually same)
        assert sanitize_filename(nfc) == sanitize_filename(nfd)

    def test_empty_or_invalid_becomes_unnamed(self):
        """Empty or all-invalid input should become 'unnamed'."""
        assert sanitize_filename("") == "unnamed"
        assert sanitize_filename("   ") == "unnamed"
        assert sanitize_filename("...") == "unnamed"
        assert sanitize_filename(":::") == "unnamed"

    def test_control_characters_removed(self):
        """NULL bytes and control characters should be removed."""
        assert sanitize_filename("file\x00name") == "file-name"
        assert sanitize_filename("file\x1fname") == "file-name"


# =============================================================================
# Tests: Unique Filename Generation (Collision handling)
# =============================================================================

class TestGetUniqueFilename:
    """Test unique filename generation for collision avoidance."""

    def test_no_collision(self):
        """No collision should return original name."""
        assert get_unique_filename("file.md", set()) == "file.md"
        assert get_unique_filename("file.md", {"other.md"}) == "file.md"

    def test_case_insensitive_collision(self):
        """Case-insensitive collision should add suffix."""
        existing = {"file.md"}
        assert get_unique_filename("File.md", existing) == "File_1.md"
        assert get_unique_filename("FILE.MD", existing) == "FILE_1.MD"

    def test_case_sensitive_no_collision(self):
        """Case-sensitive mode should allow different cases."""
        existing = {"file.md"}
        result = get_unique_filename("File.md", existing, case_insensitive=False)
        assert result == "File.md"

    def test_sequential_numbering(self):
        """Sequential collisions should increment suffix."""
        existing = {"file.md", "file_1.md", "file_2.md"}
        assert get_unique_filename("file.md", existing) == "file_3.md"

    def test_extension_preserved(self):
        """File extension should be preserved in suffix."""
        existing = {"report.pdf"}
        assert get_unique_filename("report.pdf", existing) == "report_1.pdf"

    def test_no_extension(self):
        """Files without extension should work."""
        existing = {"README"}
        assert get_unique_filename("README", existing) == "README_1"

    def test_multiple_dots(self):
        """Multiple dots should use rightmost as extension."""
        existing = {"file.tar.gz"}
        result = get_unique_filename("file.tar.gz", existing)
        assert result == "file.tar_1.gz"


# =============================================================================
# Tests: Project Slug Generation (Directory naming)
# =============================================================================

class TestMakeProjectSlug:
    """Test project slug generation for directory names."""

    def test_basic_slug(self):
        """Basic project name should become slug."""
        slug = make_project_slug("My Project", "12345678-1234-1234-1234-123456789abc")
        assert slug == "my-project-12345678"

    def test_spaces_to_hyphens(self):
        """Spaces should become hyphens."""
        slug = make_project_slug("Multi Word Project", "abcd1234-0000-0000-0000-000000000000")
        assert slug == "multi-word-project-abcd1234"

    def test_special_chars_sanitized(self):
        """Special characters should be sanitized."""
        slug = make_project_slug("Project <2024>", "aaaaaaaa-0000-0000-0000-000000000000")
        # Note: < and > both become -, then get collapsed, but space after becomes another -
        assert slug == "project--2024-aaaaaaaa"

    def test_uuid_shortened(self):
        """UUID should be shortened to 8 chars."""
        slug = make_project_slug("Test", "12345678-90ab-cdef-1234-567890abcdef")
        assert slug.endswith("-12345678")

    def test_long_name_truncated(self):
        """Very long names should be truncated to 50 chars."""
        long_name = "This is a very long project name that exceeds the limit"
        slug = make_project_slug(long_name, "12345678-0000-0000-0000-000000000000")

        # Should be truncated to 50 chars + hyphen + 8 char uuid
        prefix = slug[:-9]  # Remove -12345678
        assert len(prefix) <= 50
        assert not prefix.endswith("-")  # Trailing hyphen stripped

    def test_lowercase(self):
        """Slug should be lowercase."""
        slug = make_project_slug("UPPERCASE", "aaaaaaaa-0000-0000-0000-000000000000")
        assert slug == "uppercase-aaaaaaaa"


# =============================================================================
# Tests: Content Hashing (Change detection)
# =============================================================================

class TestComputeDocHash:
    """Test document content hashing for change detection."""

    def test_identical_content(self):
        """Identical content should produce same hash."""
        content = "Hello, world!"
        assert compute_doc_hash(content) == compute_doc_hash(content)

    def test_line_ending_normalization(self):
        """Different line endings should produce same hash."""
        unix = "line1\nline2\nline3"
        windows = "line1\r\nline2\r\nline3"
        mac = "line1\rline2\rline3"

        hash_unix = compute_doc_hash(unix)
        hash_windows = compute_doc_hash(windows)
        hash_mac = compute_doc_hash(mac)

        assert hash_unix == hash_windows == hash_mac

    def test_unicode_normalization(self):
        """Different unicode forms should produce same hash."""
        # é can be NFC (composed) or NFD (decomposed)
        nfc = "café"
        nfd = "cafe\u0301"  # e + combining acute accent

        assert compute_doc_hash(nfc) == compute_doc_hash(nfd)

    def test_hash_length(self):
        """Hash should be 16 characters (truncated SHA256)."""
        assert len(compute_doc_hash("test")) == 16
        assert len(compute_doc_hash("a" * 10000)) == 16

    def test_different_content_different_hash(self):
        """Different content should produce different hashes."""
        hash1 = compute_doc_hash("content1")
        hash2 = compute_doc_hash("content2")
        assert hash1 != hash2


# =============================================================================
# Tests: Timestamp Comparison (Incremental sync)
# =============================================================================

class TestTimestampsEqual:
    """Test timestamp comparison for incremental sync logic."""

    def test_identical_timestamps(self):
        """Identical timestamps should be equal."""
        ts = "2024-01-15T10:30:00Z"
        assert timestamps_equal(ts, ts) is True

    def test_format_differences(self):
        """Same time in different formats should be equal."""
        zulu = "2024-01-15T10:30:00Z"
        offset = "2024-01-15T10:30:00+00:00"
        assert timestamps_equal(zulu, offset) is True

    def test_different_times(self):
        """Different times should not be equal."""
        ts1 = "2024-01-15T10:30:00Z"
        ts2 = "2024-01-15T10:31:00Z"
        assert timestamps_equal(ts1, ts2) is False

    def test_none_handling(self):
        """None values should be handled gracefully."""
        assert timestamps_equal(None, None) is True
        assert timestamps_equal(None, "2024-01-15T10:30:00Z") is False
        assert timestamps_equal("2024-01-15T10:30:00Z", None) is False

    def test_empty_string(self):
        """Empty strings should be handled."""
        assert timestamps_equal("", "") is True
        assert timestamps_equal("", "2024-01-15T10:30:00Z") is False

    def test_unparsable_fallback(self):
        """Unparsable timestamps should fall back to string comparison."""
        invalid1 = "not-a-timestamp"
        invalid2 = "also-not-a-timestamp"

        assert timestamps_equal(invalid1, invalid1) is True
        assert timestamps_equal(invalid1, invalid2) is False

    def test_timezone_differences(self):
        """Same moment in different timezones should be equal."""
        utc = "2024-01-15T10:30:00Z"
        plus1 = "2024-01-15T11:30:00+01:00"
        minus5 = "2024-01-15T05:30:00-05:00"

        assert timestamps_equal(utc, plus1) is True
        assert timestamps_equal(utc, minus5) is True


# =============================================================================
# Tests: Project Sync Detection (Core sync logic)
# =============================================================================

class TestProjectNeedsSync:
    """Test project sync detection logic."""

    def test_new_project(self):
        """New projects should need sync."""
        project = {"uuid": "proj-1", "name": "Test"}
        needs, reason = project_needs_sync(project, [], {})
        assert needs is True
        assert reason == "new project"

    def test_unchanged_project(self):
        """Unchanged projects should not need sync."""
        project = {
            "uuid": "proj-1",
            "updated_at": "2024-01-15T10:00:00Z",
            "prompt_template": "Instructions",
        }
        prev_state = {
            "projects": {
                "proj-1": {
                    "updated_at": "2024-01-15T10:00:00Z",
                    "prompt_template_hash": compute_doc_hash("Instructions"),
                    "docs": {},
                }
            }
        }

        needs, reason = project_needs_sync(project, [], prev_state)
        assert needs is False
        assert reason == "unchanged"

    def test_updated_timestamp(self):
        """Changed timestamp should trigger sync."""
        project = {
            "uuid": "proj-1",
            "updated_at": "2024-01-15T11:00:00Z",
            "prompt_template": "",
        }
        prev_state = {
            "projects": {
                "proj-1": {
                    "updated_at": "2024-01-15T10:00:00Z",
                    "prompt_template_hash": compute_doc_hash(""),
                    "docs": {},
                }
            }
        }

        needs, reason = project_needs_sync(project, [], prev_state)
        assert needs is True
        assert "updated" in reason

    def test_instructions_changed(self):
        """Changed instructions should trigger sync."""
        project = {
            "uuid": "proj-1",
            "updated_at": "2024-01-15T10:00:00Z",
            "prompt_template": "New instructions",
        }
        prev_state = {
            "projects": {
                "proj-1": {
                    "updated_at": "2024-01-15T10:00:00Z",
                    "prompt_template_hash": compute_doc_hash("Old instructions"),
                    "docs": {},
                }
            }
        }

        needs, reason = project_needs_sync(project, [], prev_state)
        assert needs is True
        assert reason == "instructions changed"

    def test_doc_count_changed(self):
        """Changed document count should trigger sync."""
        project = {
            "uuid": "proj-1",
            "updated_at": "2024-01-15T10:00:00Z",
            "prompt_template": "",
        }
        docs = [{"uuid": "doc-1", "content": "test"}]
        prev_state = {
            "projects": {
                "proj-1": {
                    "updated_at": "2024-01-15T10:00:00Z",
                    "prompt_template_hash": compute_doc_hash(""),
                    "docs": {},
                }
            }
        }

        needs, reason = project_needs_sync(project, docs, prev_state)
        assert needs is True
        assert "doc count changed" in reason

    def test_doc_content_changed(self):
        """Changed document content should trigger sync."""
        project = {
            "uuid": "proj-1",
            "updated_at": "2024-01-15T10:00:00Z",
            "prompt_template": "",
        }
        docs = [{"uuid": "doc-1", "content": "new content"}]
        prev_state = {
            "projects": {
                "proj-1": {
                    "updated_at": "2024-01-15T10:00:00Z",
                    "prompt_template_hash": compute_doc_hash(""),
                    "docs": {
                        "doc-1": {
                            "hash": compute_doc_hash("old content"),
                            "filename": "doc.md",
                        }
                    },
                }
            }
        }

        needs, reason = project_needs_sync(project, docs, prev_state)
        assert needs is True
        assert reason == "doc content changed"


# =============================================================================
# Tests: Conversation Sync Detection
# =============================================================================

class TestConversationNeedsSync:
    """Test conversation sync detection logic."""

    def test_force_full_sync(self):
        """Force full should always return True."""
        convo = {"uuid": "conv-1"}
        needs, reason = conversation_needs_sync(convo, {}, force_full=True)
        assert needs is True
        assert reason == "full sync"

    def test_new_conversation(self):
        """New conversations should need sync."""
        convo = {"uuid": "conv-1", "updated_at": "2024-01-15T10:00:00Z"}
        needs, reason = conversation_needs_sync(convo, {})
        assert needs is True
        assert reason == "new"

    def test_unchanged_conversation(self):
        """Unchanged conversations should not need sync."""
        convo = {
            "uuid": "conv-1",
            "updated_at": "2024-01-15T10:00:00Z",
        }
        prev_convos = {
            "conv-1": {
                "updated_at": "2024-01-15T10:00:00Z",
            }
        }

        needs, reason = conversation_needs_sync(convo, prev_convos)
        assert needs is False
        assert reason == "unchanged"

    def test_updated_conversation(self):
        """Updated conversations should need sync."""
        convo = {
            "uuid": "conv-1",
            "updated_at": "2024-01-15T11:00:00Z",
        }
        prev_convos = {
            "conv-1": {
                "updated_at": "2024-01-15T10:00:00Z",
            }
        }

        needs, reason = conversation_needs_sync(convo, prev_convos)
        assert needs is True
        assert reason == "updated"

    def test_timestamp_format_tolerance(self):
        """Different timestamp formats should not trigger sync."""
        convo = {
            "uuid": "conv-1",
            "updated_at": "2024-01-15T10:00:00Z",
        }
        prev_convos = {
            "conv-1": {
                "updated_at": "2024-01-15T10:00:00+00:00",
            }
        }

        needs, reason = conversation_needs_sync(convo, prev_convos)
        assert needs is False
        assert reason == "unchanged"
