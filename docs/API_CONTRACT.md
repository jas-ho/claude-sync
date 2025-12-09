# Claude.ai API Contract

This document describes the assumed API response structure for claude-sync. The code makes many assumptions about field existence and types. If Claude.ai changes these fields, the sync may fail silently or crash.

**Last Updated:** 2025-12-09

______________________________________________________________________

## Overview

The claude-sync tool relies on several undocumented Claude.ai API endpoints. These endpoints return JSON responses with specific field structures that the code assumes will be present. This document catalogs all such assumptions to help future maintainers understand failure modes and debug API changes.

## Bootstrap Endpoint

**Endpoint:** `GET /api/bootstrap`

**Purpose:** Discover available organizations for the authenticated user

**Code Location:** `discover_organizations()` (lines 501-523)

### Expected Response Structure

```json
{
  "account": {
    "memberships": [
      {
        "organization": {
          "uuid": "string",
          "name": "string"
        }
      }
    ]
  }
}
```

### Field Assumptions

| Field Path | Type | Required? | Default | Usage | Failure Mode |
|------------|------|-----------|---------|-------|--------------|
| `account` | dict | Yes | N/A | Extract memberships | Returns `{}` if missing, empty org list |
| `account.memberships` | list | Yes | `[]` | Iterate organizations | Returns empty list if missing |
| `account.memberships[].organization` | dict | Yes | `{}` | Extract org data | Skipped if missing |
| `account.memberships[].organization.uuid` | string | Yes | None | Org identification | Org excluded if missing (validated with `if org.get("uuid")`) |
| `account.memberships[].organization.name` | string | No | `"Unknown"` | Display name | Falls back to "Unknown" |

### Validation

- Response type checked: `isinstance(data, dict)` (line 513)
- UUID presence validated before adding to org list (line 520)
- Missing fields handled gracefully with `.get()` and defaults

______________________________________________________________________

## Projects List Endpoint

**Endpoint:** `GET /api/organizations/{org_uuid}/projects`

**Purpose:** Fetch list of all projects (basic metadata only, no prompt_template)

**Code Location:** `fetch_projects()` (lines 526-543)

### Expected Response

```json
[
  {
    "uuid": "string",
    "name": "string",
    "description": "string",
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp",
    "is_private": boolean
  }
]
```

### Field Assumptions

| Field | Type | Required? | Default | Usage | Failure Mode |
|-------|------|-----------|---------|-------|--------------|
| `uuid` | string | **YES** | N/A | Project identification, slug generation | **KeyError crash** (line 1766: `project["uuid"]`) |
| `name` | string | No | `"Unknown"` / `"Unnamed Project"` | Display, slug generation | Falls back to default |
| `description` | string | No | `""` | Saved to meta.json | Empty string if missing |
| `created_at` | string | No | None | Saved to meta.json, status display | None if missing |
| `updated_at` | string | No | `""` | Incremental sync detection, sorting | Empty string if missing, affects sync logic |
| `is_private` | boolean | No | `true` | Saved to meta.json | Defaults to true |

### Validation

- Response type checked: `isinstance(projects, list)` (line 539)
- UUID accessed directly without `.get()` - **WILL CRASH** if missing
- Other fields use `.get()` with defaults

### Critical Issue

**Line 1766:** `project_uuid = project["uuid"]` - Direct dictionary access without validation. If API removes `uuid` field, sync will crash with `KeyError`.

**Line 1731:** `if filter_str in p["uuid"].lower()...` - Another direct access point.

______________________________________________________________________

## Project Details Endpoint

**Endpoint:** `GET /api/organizations/{org_uuid}/projects/{project_uuid}`

**Purpose:** Fetch full project metadata including prompt_template (project instructions)

**Code Location:** `fetch_project_details()` (lines 546-565), `write_project_output()` (lines 882-1062)

### Expected Response

```json
{
  "uuid": "string",
  "name": "string",
  "description": "string",
  "prompt_template": "string",
  "created_at": "ISO8601 timestamp",
  "updated_at": "ISO8601 timestamp",
  "is_private": boolean
}
```

### Field Assumptions

| Field | Type | Required? | Default | Usage | Failure Mode |
|-------|------|-----------|---------|-------|--------------|
| `uuid` | string | **YES** | N/A | Directory validation, collision detection | **KeyError crash** (line 907: `project["uuid"]`) |
| `name` | string | No | `"Unnamed Project"` | Slug generation, CLAUDE.md header | Falls back to default |
| `prompt_template` | string | No | `""` | CLAUDE.md content, change detection | Empty CLAUDE.md with fallback message |
| `description` | string | No | `""` | Saved to meta.json | Empty string |
| `created_at` | string | No | None | Saved to meta.json | None |
| `updated_at` | string | No | None | Saved to meta.json, sync detection | None, breaks incremental sync |
| `is_private` | boolean | No | `true` | Saved to meta.json | Defaults to true |

### Validation

- Response type checked: `isinstance(project, dict)` (line 562)
- UUID accessed directly - **WILL CRASH** if missing (multiple locations)
- Other fields use `.get()` with defaults

### Critical Issues

**Line 907:** `project_uuid = project["uuid"]` - Direct access, will crash if missing

**Line 936:** `existing_uuid != project.get("uuid")` - Inconsistent: uses `.get()` here but direct access elsewhere

______________________________________________________________________

## Project Documents Endpoint

**Endpoint:** `GET /api/organizations/{org_uuid}/projects/{project_uuid}/docs?tree=true`

**Purpose:** Fetch all documents for a project

**Code Location:** `fetch_project_docs()` (lines 568-589), `write_project_output()` doc processing (lines 994-1061)

### Expected Response

```json
[
  {
    "uuid": "string",
    "file_name": "string",
    "content": "string",
    "created_at": "ISO8601 timestamp"
  }
]
```

### Field Assumptions

| Field | Type | Required? | Default | Usage | Failure Mode |
|-------|------|-----------|---------|-------|--------------|
| `uuid` | string | No | `""` | Rename detection, change tracking | Empty string, affects incremental sync |
| `file_name` | string | No | `"untitled.md"` | Document filename | Falls back to "untitled.md" |
| `filename` | string | No | N/A | Fallback field name | Alternative to `file_name` |
| `content` | string | No | `""` | Document content, hash computation | Empty content |
| `created_at` | string | No | N/A | Not currently used | Ignored |

### Validation

- Response type checked: `isinstance(docs, list)` (line 585)
- All fields use `.get()` with defaults - **NO CRASH RISK**
- Supports both `file_name` and `filename` (API inconsistency workaround)

### Size Limits

- Max document size: 10MB (line 1011-1014) - documents exceeding this are skipped with warning
- Uses `len(content.encode('utf-8'))` for size calculation

### Notes

**Line 1016:** `doc_filename = doc.get("file_name") or doc.get("filename") or "untitled.md"` - Good defensive programming, handles API field name variations

______________________________________________________________________

## Project Conversations Endpoint

**Endpoint:** `GET /api/organizations/{org_uuid}/projects/{project_uuid}/conversations?tree=true`

**Purpose:** Fetch conversation list for a project (metadata only, not messages)

**Code Location:** `fetch_project_conversations()` (lines 592-613), conversation sync (lines 1800-1883)

### Expected Response

```json
[
  {
    "uuid": "string",
    "name": "string",
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
  }
]
```

### Field Assumptions

| Field | Type | Required? | Default | Usage | Failure Mode |
|-------|------|-----------|---------|-------|--------------|
| `uuid` | string | No | None | Conversation identification | Skipped if missing (line 1814: `if not convo_uuid`) |
| `name` | string | No | `"Untitled"` | Filename, display | Falls back to "Untitled" |
| `created_at` | string | No | `""` | Saved to index | Empty string |
| `updated_at` | string | No | `""` | Incremental sync detection | Empty string, affects sync logic |

### Validation

- Response type checked: `isinstance(convos, list)` (line 609)
- UUID checked before processing (line 1814)
- All fields use `.get()` with defaults - **NO CRASH RISK**

______________________________________________________________________

## Conversation Details Endpoint

**Endpoint:** `GET /api/organizations/{org_uuid}/chat_conversations/{conversation_uuid}?rendering_mode=messages&render_all_tools=true`

**Purpose:** Fetch full conversation with all messages

**Code Location:** `fetch_conversation()` (lines 616-636), `format_conversation_markdown()` (lines 1339-1421)

### Expected Response

```json
{
  "uuid": "string",
  "name": "string",
  "created_at": "ISO8601 timestamp",
  "updated_at": "ISO8601 timestamp",
  "chat_messages": [
    {
      "sender": "human|assistant",
      "created_at": "ISO8601 timestamp",
      "content": [
        {
          "type": "text",
          "text": "string"
        },
        {
          "type": "thinking",
          "thinking": "string"
        }
      ],
      "text": "string"
    }
  ]
}
```

### Field Assumptions

| Field Path | Type | Required? | Default | Usage | Failure Mode |
|------------|------|-----------|---------|-------|--------------|
| `uuid` | string | No | `"unknown"` | Markdown frontmatter | Falls back to "unknown" |
| `name` | string | No | `"Untitled"` | Markdown title, filename | Falls back to "Untitled" |
| `created_at` | string | No | `""` | Markdown frontmatter | Empty string |
| `updated_at` | string | No | `""` | Markdown frontmatter | Empty string |
| `chat_messages` | list | No | `[]` | Message iteration | Empty list, empty conversation |
| `chat_messages[].sender` | string | No | `"unknown"` | Message header formatting | Falls back to "unknown" |
| `chat_messages[].created_at` | string | No | `""` | Timestamp display | Omitted if missing |
| `chat_messages[].content` | list | No | `[]` | Message content extraction | Falls back to `text` field |
| `chat_messages[].content[].type` | string | No | `""` | Block type detection | Empty string, block ignored |
| `chat_messages[].content[].text` | string | No | `""` | Text content | Empty string |
| `chat_messages[].content[].thinking` | string | No | `""` | Extended thinking content | Empty string |
| `chat_messages[].text` | string | No | `""` | Legacy fallback | Used if `content` array empty |

### Validation

- Response type checked: `isinstance(convo, dict)` (line 633)
- All fields use `.get()` with defaults - **NO CRASH RISK**
- Message count checked against limit: 10,000 messages (line 1831)

### Content Structure Evolution

The code handles both old and new message formats:

- **New format:** `content` array with typed blocks (`text`, `thinking`)
- **Old format:** Plain `text` field

This dual support (lines 1375-1394) provides backward compatibility.

______________________________________________________________________

## All Conversations Endpoint

**Endpoint:** `GET /api/organizations/{org_uuid}/chat_conversations`

**Purpose:** Fetch all conversations (both project and standalone)

**Code Location:** `fetch_all_conversations()` (lines 639-656), `fetch_standalone_conversations()` (lines 659-681)

### Expected Response

```json
[
  {
    "uuid": "string",
    "name": "string",
    "project_uuid": "string | null",
    "created_at": "ISO8601 timestamp",
    "updated_at": "ISO8601 timestamp"
  }
]
```

### Field Assumptions

| Field | Type | Required? | Default | Usage | Failure Mode |
|-------|------|-----------|---------|-------|--------------|
| `uuid` | string | No | None | Conversation identification | Skipped if missing |
| `name` | string | No | `"Untitled"` | Display | Falls back to "Untitled" |
| `project_uuid` | string/null | No | None | Standalone filtering | Treated as standalone if missing/null |
| `created_at` | string | No | `""` | Saved to index | Empty string |
| `updated_at` | string | No | `""` | Sync detection | Empty string |

### Validation

- Response type checked: `isinstance(convos, list)` (line 651)
- All fields use `.get()` - **NO CRASH RISK**

### Filtering Logic

**Line 676-678:** Standalone conversations are those where:

```python
not c.get("project_uuid") or c.get("project_uuid") not in project_uuids
```

This means missing `project_uuid` is treated as standalone.

______________________________________________________________________

## Summary of Critical Issues

### High Risk (Will Crash)

1. **Project UUID** - Direct dictionary access without validation:
   - Line 907: `project["uuid"]` in `write_project_output()`
   - Line 1731: `p["uuid"]` in project filtering
   - Line 1766: `project["uuid"]` in sync loop

### Medium Risk (Silent Failures)

1. **Missing `updated_at`** - Breaks incremental sync:

   - Projects without `updated_at` get empty string, always appear unchanged
   - Conversations without `updated_at` always appear unchanged
   - Affects `project_needs_sync()` and `conversation_needs_sync()`

1. **Missing `name`** - Affects slug generation:

   - Falls back to "Unknown" or "Unnamed Project"
   - Could cause slug collisions if multiple unnamed projects exist

### Low Risk (Handled Gracefully)

1. **Optional fields** - All use `.get()` with sensible defaults:
   - `prompt_template`, `description`, `is_private`
   - `file_name`, `content`
   - Conversation fields

______________________________________________________________________

## Recommendations for Robustness

### Immediate Fixes

1. **Replace direct UUID access** with validated `.get()`:

   ```python
   # Instead of: project_uuid = project["uuid"]
   project_uuid = project.get("uuid")
   if not project_uuid:
       log.error(f"Project missing UUID: {project}")
       continue
   ```

1. **Validate response structure** before processing:

   ```python
   def validate_project(project: dict) -> bool:
       required = ["uuid"]
       for field in required:
           if field not in project:
               log.error(f"Invalid project: missing required field '{field}'")
               return False
       return True
   ```

### Long-term Improvements

1. **Schema validation** - Add JSON schema validation for API responses
1. **Field versioning** - Track API response structure version in sync state
1. **Defensive defaults** - Ensure all field access uses `.get()` consistently
1. **Integration tests** - Mock API responses with missing fields to test resilience

______________________________________________________________________

## Testing Recommendations

To test resilience to API changes:

1. **Mock responses with missing fields:**

   - Remove `uuid` from projects
   - Remove `updated_at` from projects/conversations
   - Remove `prompt_template` from project details
   - Remove `content` from documents

1. **Test empty responses:**

   - Empty project list `[]`
   - Empty document list `[]`
   - Empty conversation list `[]`

1. **Test malformed responses:**

   - Wrong response types (dict instead of list, vice versa)
   - Null values in required fields
   - Missing nested structures

______________________________________________________________________

## Change History

- **2025-12-09:** Initial documentation based on claude_sync.py analysis
