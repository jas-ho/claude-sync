# Setup Sync Command

Help the user integrate their synced Claude.ai web app projects with Claude Code.

## Overview

This command helps you connect synced projects from claude.ai to Claude Code by adding @import statements to your global CLAUDE.md file. Once integrated, project instructions and documentation from your web projects become available in all Claude Code sessions.

## Steps

### 1. Check for synced projects

First, check if synced projects exist:
- Look for `~/.local/share/claude-sync/` directory (the default sync location)
- If not found, explain that the user needs to run `claude_sync.py` first to sync their projects
- Check if `index.json` exists in that directory

### 2. List available projects

If synced projects are found:
- Read `~/.local/share/claude-sync/index.json` to get the list of projects
- For each project, show:
  - Project name
  - Whether it has a CLAUDE.md file (project instructions)
  - Number of documents synced
  - Last sync timestamp
- Present this information in a clear, readable format

### 3. Suggest integration

For each project that has a CLAUDE.md file:
- Suggest adding an @import statement to `~/.claude/CLAUDE.md`
- Format: `@~/.local/share/claude-sync/<project-slug>/CLAUDE.md`
- Explain what each import does (makes those project instructions available globally)
- Let the user know they can also use relative paths if preferred

**Example integration:**
```markdown
# In ~/.claude/CLAUDE.md

## Synced Web Projects

@~/.local/share/claude-sync/research-workspace/CLAUDE.md
@~/.local/share/claude-sync/client-project/CLAUDE.md
```

### 4. Check existing imports

If `~/.claude/CLAUDE.md` already exists:
- Read the file and check for existing @import statements pointing to synced projects
- Report which projects are already integrated
- Only suggest adding imports for projects that aren't already imported
- Avoid duplicating imports

If the file doesn't exist:
- Explain that the user can create it to add global instructions
- Offer to show example content if they want to create it

## Guidelines

- **Be helpful and informative**: Explain what each step accomplishes and why it matters
- **Make suggestions, not assumptions**: Present options and let the user decide what to import
- **Don't automatically modify files**: Show the user what to add, but let them make the changes
- **Handle errors gracefully**: If directories don't exist or files can't be read, provide clear guidance on what to do next
- **Expand tildes**: Remember to expand `~` to the actual home directory path when reading files

## Expected User Experience

User runs `/setup-sync` and gets:
1. Status of their synced projects
2. Clear list of what's available
3. Specific suggestions for integration
4. Confirmation of what's already set up (if anything)
5. Next steps to make it all work
