import json
from pathlib import Path
from datetime import datetime


def sanitize_filename(filename):
    """Convert filename to a valid filesystem name while preserving original name."""
    # Only remove truly invalid characters, keep spaces and other special characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, "")
    return filename


def get_unique_filename(base_path, filename):
    """Get a unique filename by appending a number if the file already exists."""
    if not base_path.exists():
        return filename

    name = base_path.stem
    suffix = base_path.suffix
    counter = 1

    while base_path.exists():
        base_path = base_path.with_name(f"{name}_{counter}{suffix}")
        counter += 1

    return base_path.name


def create_markdown_file(path, content, title):
    """Create a markdown file with frontmatter."""
    frontmatter = f"""---
title: {title}
created_at: {datetime.now().isoformat()}
---

"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(frontmatter)
        f.write(content)


def process_metadata_file(metadata_path):
    """Process a single metadata.json file and create corresponding markdown files."""
    # Read the metadata file
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Get the project directory (parent of metadata.json)
    project_dir = metadata_path.parent
    metadata_dir = project_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)

    # Create prompt template markdown if it exists
    if metadata.get("prompt_template"):
        prompt_path = metadata_dir / "prompt_template.md"
        create_markdown_file(
            prompt_path,
            metadata["prompt_template"],
            f"Prompt Template - {metadata['name']}",
        )
        print(f"Created prompt template for {metadata['name']}")

    # Create description markdown if it exists
    if metadata.get("description"):
        desc_path = metadata_dir / "description.md"
        create_markdown_file(
            desc_path,
            metadata["description"],
            f"Project Description - {metadata['name']}",
        )
        print(f"Created description for {metadata['name']}")

    # Update metadata.json to reference the new files
    metadata["files"] = {
        "prompt_template": "metadata/prompt_template.md"
        if metadata.get("prompt_template")
        else None,
        "description": "metadata/description.md"
        if metadata.get("description")
        else None,
    }

    # Remove the raw content from metadata
    if "prompt_template" in metadata:
        del metadata["prompt_template"]
    if "description" in metadata:
        del metadata["description"]

    # Write updated metadata back to file
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    print(f"Updated metadata.json for {metadata['name']}")


def create_project_structure(projects_data):
    """Create directory structure and markdown files for each project."""
    # Create base output directory
    output_dir = Path("processed_projects")
    output_dir.mkdir(exist_ok=True)

    # Track used filenames within each project to handle collisions
    project_filename_tracker = {}

    for project in projects_data:
        # Create project directory with sanitized name
        project_dir = output_dir / sanitize_filename(project["name"])
        project_dir.mkdir(exist_ok=True)

        # Create docs directory
        docs_dir = project_dir / "docs"
        docs_dir.mkdir(exist_ok=True)

        # Create project metadata file
        metadata = {
            "name": project["name"],
            "is_private": project["is_private"],
            "is_starter_project": project["is_starter_project"],
            "created_at": project["created_at"],
            "updated_at": project["updated_at"],
            "creator": project["creator"],
            "prompt_template": project.get("prompt_template"),
            "description": project.get("description"),
        }

        with open(project_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        # Initialize filename tracker for this project
        project_filename_tracker[project["name"]] = set()

        # Process each document
        for doc in project["docs"]:
            # Use original filename, just sanitize invalid characters
            original_filename = doc["filename"]
            doc_filename = sanitize_filename(original_filename)

            # Ensure .md extension
            if not doc_filename.lower().endswith(".md"):
                doc_filename += ".md"

            # Create full path
            doc_path = docs_dir / doc_filename

            # Handle filename collisions
            if doc_filename in project_filename_tracker[project["name"]]:
                doc_path = docs_dir / get_unique_filename(doc_path, doc_filename)
                print(
                    f"Warning: Filename collision detected in project '{project['name']}'. Using: {doc_path.name}"
                )

            # Add to tracker
            project_filename_tracker[project["name"]].add(doc_path.name)

            # Add metadata as frontmatter
            frontmatter = f"""---
created_at: {doc["created_at"]}
---

"""

            # Write the content with frontmatter
            with open(doc_path, "w", encoding="utf-8") as f:
                f.write(frontmatter)
                f.write(doc["content"])


def main():
    print("Starting project processing...")

    # Read the projects.json file
    with open(
        "Claude-data-2025-04-03-12-15-45/projects.json", "r", encoding="utf-8"
    ) as f:
        projects_data = json.load(f)

    # Process the projects
    create_project_structure(projects_data)
    print("\nInitial project processing complete!")

    print("\nStarting metadata extraction...")
    # Find all metadata.json files in the processed_projects directory
    metadata_files = list(Path("processed_projects").rglob("metadata.json"))

    if not metadata_files:
        print("No metadata.json files found in the processed_projects directory.")
        return

    print(f"Found {len(metadata_files)} metadata.json files")

    # Process each metadata file
    for metadata_path in metadata_files:
        try:
            process_metadata_file(metadata_path)
        except Exception as e:
            print(f"Error processing {metadata_path}: {str(e)}")

    print("\nProcessing complete! Check the 'processed_projects' directory.")


if __name__ == "__main__":
    main()
