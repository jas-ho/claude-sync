# Tests

High-value smoke and integration tests for claude-sync core functions.

## Running Tests

```bash
# Run all tests
uv run --with pytest pytest tests/

# Run with verbose output
uv run --with pytest pytest tests/ -v

# Run specific test class
uv run --with pytest pytest tests/ -k TestSanitizeFilename

# Run specific test
uv run --with pytest pytest tests/test_core_functions.py::TestSanitizeFilename::test_windows_reserved_names
```

## Test Coverage

### High Priority (Cross-platform safety)

- **Filename Sanitization** (8 tests)
  - Invalid character handling
  - Windows reserved names (CON, PRN, COM1, etc.)
  - Unicode normalization (NFC)
  - Length truncation with hash
  - Control character removal

- **Unique Filename Generation** (7 tests)
  - Case-sensitive/insensitive collision handling
  - Sequential numbering
  - Extension preservation

- **Project Slug Generation** (6 tests)
  - Special character sanitization
  - UUID shortening
  - Length truncation
  - Lowercase conversion

### Content Change Detection

- **Document Hashing** (5 tests)
  - Line ending normalization (CRLF/LF/CR)
  - Unicode normalization
  - Hash consistency

- **Timestamp Comparison** (7 tests)
  - Format differences (Z vs +00:00)
  - Timezone handling
  - None/empty string handling
  - Unparseable fallback

### Core Sync Logic

- **Project Sync Detection** (6 tests)
  - New project detection
  - Timestamp changes
  - Instruction changes
  - Document count changes
  - Document content changes

- **Conversation Sync Detection** (5 tests)
  - New conversation detection
  - Update detection
  - Force full sync
  - Timestamp format tolerance

## Design Philosophy

These tests focus on **high-value scenarios** that:
1. Catch real cross-platform issues (Windows reserved names, path safety)
2. Verify incremental sync correctness (avoiding unnecessary re-syncs)
3. Test edge cases in string handling (unicode, line endings, collisions)
4. Are pure functions requiring no API mocking

Tests deliberately avoid:
- Low-value "coverage for coverage's sake" tests
- Functions requiring complex API mocking
- Trivial getters/setters
- I/O operations without clear value
