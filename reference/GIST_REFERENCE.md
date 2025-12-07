# Original Gist Reference

The claude-sync project is based on this gist:
https://gist.github.com/jas-ho/f95abd89d4e007eac9ee821d7c2a3d0b

## Key Features from Gist

- UV script with inline dependencies
- Browser cookie extraction (Edge/Chrome)
- Parallel chat fetching (MAX_WORKERS=16)
- Exports to ZIP with structure:
  ```
  projects/
  ├── <name-slug>-<uuid>/
  │   ├── meta.json
  │   ├── instructions.md
  │   ├── docs_index.json
  │   ├── docs/
  │   └── chats/
  └── projects.json
  ```

## Known Issues (from gist comments)

- Forward slashes in document titles not properly escaped for filenames
- Need robust filename sanitization for cross-platform compatibility

## Adaptation Notes

For claude-sync, we modify this to:
1. Output to directory (not ZIP) for git tracking
2. Configurable output location
3. Add incremental sync capability
4. More robust filename handling
