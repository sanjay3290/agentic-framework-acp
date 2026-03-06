# Skills System

## Overview

Skills are reusable agent capabilities that follow the [agentskills.io](https://agentskills.io) standard. A skill is a folder containing a `SKILL.md` file with YAML frontmatter and markdown instructions. The agentskills.io standard is supported by over 30 AI agents, making skills portable across tools and frameworks.

In the ACP Agent Framework, skills allow you to define composable, shareable blocks of agent behavior. When an agent references one or more skills, the framework loads each skill from the filesystem, resolves dependencies in topological order, and prepends the combined skill instructions to the agent's prompt. This means an agent can gain new capabilities -- code review practices, messaging integrations, formatting conventions -- simply by referencing skill names.

Skills are purely declarative: they consist of a markdown file with optional YAML metadata. There is no code to compile or deploy. Any agent that understands the agentskills.io standard can consume the same skill definitions.

---

## Skill Structure

A skill is a directory containing at minimum a `SKILL.md` file. The directory may also contain helper scripts, templates, or any other supporting files the skill instructions reference.

```
.agents/skills/my-skill/
|-- SKILL.md          # Required: YAML frontmatter + markdown instructions
|-- scripts/          # Optional: helper scripts referenced by instructions
|-- templates/        # Optional: templates for code generation, messages, etc.
```

The directory name serves as the skill's lookup key. When you reference a skill by name (e.g., `"my-skill"`), the framework searches for a directory with that name in the standard skill locations and reads the `SKILL.md` file within it.

### Minimal Example

A valid skill can be as simple as a single file:

```
.agents/skills/code-review/
|-- SKILL.md
```

### Full Example

A more complete skill might include scripts and templates:

```
.agents/skills/google-chat/
|-- SKILL.md
|-- scripts/
|   |-- chat.py
|   |-- auth.py
|-- templates/
|   |-- message.json
```

---

## SKILL.md Format

A `SKILL.md` file has two parts:

1. **YAML frontmatter** -- delimited by `---` lines at the top of the file. Contains structured metadata about the skill.
2. **Markdown body** -- everything after the closing `---`. Contains the actual instructions the agent will follow.

### Full Format

```markdown
---
name: my-skill
description: A reusable agent capability
license: MIT
dependencies:
  - base-skill
  - helper-skill
metadata:
  author: you
  version: "1.0"
---

# My Skill Instructions

Detailed markdown instructions the agent will follow.

## Steps

1. First, do this.
2. Then, do that.
3. Finally, return results.
```

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | Human-readable name of the skill. Defaults to the folder name if omitted. |
| `description` | string | No | Short description of what the skill does. Used for discovery and documentation. Defaults to an empty string. |
| `license` | string | No | License identifier (e.g., `MIT`, `Apache-2.0`). Stored in the `metadata` dict on the parsed `Skill` object. |
| `dependencies` | list of strings | No | Names of other skills this skill depends on. Dependencies are loaded recursively before this skill. Defaults to an empty list. |
| `metadata` | dict | No | Arbitrary key-value pairs for custom metadata (author, version, tags, etc.). Any frontmatter fields that are not `name`, `description`, or `dependencies` are also placed into the metadata dict. |

### Frontmatter Parsing

The framework uses PyYAML (`yaml.safe_load`) to parse frontmatter when available. If PyYAML is not installed, a basic fallback parser handles simple `key: value` lines. For skills that use lists, nested objects, or other complex YAML structures in their frontmatter, PyYAML should be installed.

### Without Frontmatter

A `SKILL.md` file does not require frontmatter. If no `---` delimiters are found, the entire file content is treated as the instruction body, and all metadata fields default to empty values:

```markdown
# Simple Skill

These are the instructions. No frontmatter needed.

The skill name will be inferred from the directory name.
```

---

## Skill Discovery

The framework searches for skills in two standard locations. Project-level skills take priority over user-level skills when both define a skill with the same directory name.

### Search Locations

| Priority | Path | Scope |
|----------|------|-------|
| Higher | `<cwd>/.agents/skills/<name>/SKILL.md` | Project-level: specific to the current project |
| Lower | `~/.agents/skills/<name>/SKILL.md` | User-level: shared across all projects |

### Resolution Order

When loading a skill by name:

1. The framework first checks `<cwd>/.agents/skills/<name>/SKILL.md`.
2. If not found, it checks `~/.agents/skills/<name>/SKILL.md`.
3. If neither exists, a `FileNotFoundError` is raised listing all searched paths.

When discovering all skills (via `SkillLoader.discover`):

1. User-level skills are loaded first.
2. Project-level skills are loaded second, overriding any user-level skill with the same directory name.

This allows projects to override or customize user-level skills without modifying the originals.

### Example Directory Layout

```
# User-level skills (shared across projects)
~/.agents/skills/
|-- code-review/
|   |-- SKILL.md
|-- formatting/
|   |-- SKILL.md

# Project-level skills (specific to this project)
./my-project/.agents/skills/
|-- code-review/        # Overrides user-level code-review
|   |-- SKILL.md
|-- deploy-helper/
|   |-- SKILL.md
```

In this layout, `SkillLoader.discover("./my-project")` returns three skills: `code-review` (project version), `formatting` (user version), and `deploy-helper` (project only).

---

## SkillLoader API

The `SkillLoader` class provides three static methods for loading, discovering, and resolving skills.

### `SkillLoader.load(name, cwd)`

Load a single skill by name from the standard directories.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | `str` | The skill directory name to look up. |
| `cwd` | `str` | The current working directory, used as the base for project-level skill search. |

**Returns:** A `Skill` object with all dependencies recursively loaded.

**Raises:**
- `FileNotFoundError` -- if no `SKILL.md` is found in any standard location. The error message includes all paths that were searched.
- `ValueError` -- if a circular dependency is detected during recursive loading.

**Example:**

```python
from acp_agent_framework import SkillLoader

# Load a skill from project or user directories
skill = SkillLoader.load("code-review", cwd="/path/to/project")

print(skill.name)          # "code-review"
print(skill.description)   # "Performs thorough code reviews"
print(skill.instruction)   # Full markdown body
print(skill.path)          # PosixPath('/path/to/project/.agents/skills/code-review')
print(skill.metadata)      # {'license': 'MIT', 'metadata': {'author': 'you', 'version': '1.0'}}
print(skill.dependencies)  # [Skill(name='base-formatting', ...), ...]
```

**Error handling:**

```python
from acp_agent_framework import SkillLoader

try:
    skill = SkillLoader.load("nonexistent-skill", cwd=".")
except FileNotFoundError as e:
    print(e)
    # Skill 'nonexistent-skill' not found. Searched:
    #   - .agents/skills/nonexistent-skill/SKILL.md
    #   - /Users/you/.agents/skills/nonexistent-skill/SKILL.md
```

### `SkillLoader.discover(cwd)`

Discover all available skills from both project-level and user-level directories.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `cwd` | `str` | The current working directory for project-level skill search. |

**Returns:** `dict[str, Skill]` -- a dictionary mapping skill directory names to `Skill` objects. Project-level skills override user-level skills on name collision.

**Note:** The `discover` method does not recursively load dependencies. Each returned `Skill` has an empty `dependencies` list. Use `load` for full dependency resolution.

**Example:**

```python
from acp_agent_framework import SkillLoader

skills = SkillLoader.discover("/path/to/project")

for name, skill in skills.items():
    print(f"{name}: {skill.description}")
    print(f"  Path: {skill.path}")
    print(f"  Metadata: {skill.metadata}")
```

### `SkillLoader.resolve_all(skills)`

Return a flat list of skills in topological order, with dependencies appearing before the skills that depend on them.

**Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `skills` | `list[Skill]` | A list of `Skill` objects (typically from `SkillLoader.load`). Each skill's `dependencies` list is traversed recursively. |

**Returns:** `list[Skill]` -- a flat list of all skills (including transitive dependencies) in dependency-first topological order. Duplicates are removed (a skill appearing in multiple dependency chains is included only once).

**Raises:**
- `ValueError` -- if a circular dependency is detected in the skill graph.

**Example:**

```python
from acp_agent_framework import SkillLoader

# Load a skill with dependencies
main_skill = SkillLoader.load("main-skill", cwd=".")

# Resolve into flat topological order
resolved = SkillLoader.resolve_all([main_skill])

for skill in resolved:
    print(f"{skill.name}")
# Output (dependencies first):
#   dep-c
#   dep-a
#   dep-b
#   main-skill
```

---

## Skill Dataclass

The `Skill` class is a Python dataclass representing a parsed `SKILL.md` file.

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Skill:
    """A parsed agent skill from a SKILL.md file."""
    name: str
    description: str
    instruction: str
    path: Path
    metadata: dict[str, Any] = field(default_factory=dict)
    dependencies: list["Skill"] = field(default_factory=list)
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | The skill name. Taken from the `name` field in frontmatter, or defaults to the directory name. |
| `description` | `str` | Short description from frontmatter. Empty string if not specified. |
| `instruction` | `str` | The markdown body of the `SKILL.md` file (everything after the frontmatter). This is the text that gets injected into the agent's prompt. |
| `path` | `Path` | The filesystem path to the skill directory (not the `SKILL.md` file itself). Useful for referencing scripts or templates relative to the skill. |
| `metadata` | `dict[str, Any]` | All frontmatter fields except `name`, `description`, and `dependencies`. This includes fields like `license`, `metadata` (nested author/version), and any custom fields. |
| `dependencies` | `list[Skill]` | List of resolved `Skill` objects this skill depends on. Populated by `SkillLoader.load`; empty when created by `SkillLoader.discover`. |

### Import

```python
from acp_agent_framework import Skill
```

Or directly:

```python
from acp_agent_framework.skills import Skill
```

---

## Using Skills with Agent

The `Agent` class accepts a `skills` parameter -- a list of skill names (strings). When the agent runs, skills are loaded from the standard directories, dependencies are resolved in topological order, and all skill instructions are prepended to the agent's prompt.

### Basic Usage

```python
import asyncio
from acp_agent_framework import Agent, Context

agent = Agent(
    name="chat-agent",
    backend="claude",
    instruction="You are a helpful assistant.",
    skills=["google-chat", "code-review"],
)

ctx = Context(session_id="session-1", cwd=".")
ctx.set_input("Review the PR at https://github.com/org/repo/pull/42")

async def main():
    async for event in agent.run(ctx):
        print(f"[{event.author}] {event.content}")

asyncio.run(main())
```

### How Skill Injection Works

When `agent.run(ctx)` is called, the `resolve_instruction` method:

1. Evaluates the base instruction (handles both string and callable instructions).
2. If `skills` is non-empty, loads each skill by name using `SkillLoader.load(name, ctx.cwd)`.
3. Resolves all loaded skills into topological order using `SkillLoader.resolve_all`.
4. Formats each skill's instruction as a labeled section: `## Skill: <name>\n\n<instruction>`.
5. Joins all skill sections with `---` separators.
6. Prepends the combined skill block before the base instruction, separated by `---`.

The final prompt sent to the backend looks like:

```
## Skill: dep-a

Dependency A instructions here.

---

## Skill: dep-b

Dependency B instructions here.

---

## Skill: main-skill

Main skill instructions here.

---

You are a helpful assistant.
```

### Skills with the ToolAgent

For cases where you want to execute skill scripts directly without an LLM backend, use `ToolAgent`:

```python
import subprocess
from pathlib import Path
from acp_agent_framework import ToolAgent, Context

async def execute_chat(ctx, tools):
    """Run the google-chat skill's script directly."""
    skill_dir = Path.home() / ".agents" / "skills" / "google-chat"
    result = subprocess.run(
        ["python", "scripts/chat.py", "send-dm", "user@example.com", "hello"],
        cwd=skill_dir,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else f"Error: {result.stderr}"

agent = ToolAgent(
    name="chat-agent",
    execute=execute_chat,
)
```

---

## Skill Dependencies

Skills can declare dependencies on other skills. Dependencies are loaded recursively and their instructions are included in topological order -- all dependencies appear before the skills that depend on them.

### Declaring Dependencies

Add a `dependencies` list to the YAML frontmatter:

```yaml
---
name: advanced-review
description: Advanced code review with formatting standards
dependencies:
  - base-formatting
  - auth-helper
---

# Advanced Review Instructions

Build on the base-formatting and auth-helper skills to perform
advanced code reviews with authentication.
```

### Dependency Resolution

When `SkillLoader.load("advanced-review", cwd)` is called:

1. The loader reads `advanced-review/SKILL.md` and extracts `dependencies: [base-formatting, auth-helper]`.
2. It recursively calls `SkillLoader.load("base-formatting", cwd)` and `SkillLoader.load("auth-helper", cwd)`.
3. If those skills have their own dependencies, those are loaded recursively as well.
4. The resulting `Skill` object's `dependencies` list contains fully resolved `Skill` objects.

When the agent calls `SkillLoader.resolve_all`, the entire dependency tree is flattened into topological order.

### Transitive Dependencies

Dependencies can be deeply nested:

```
main-skill
|-- dep-a (no dependencies)
|-- dep-b
    |-- dep-c (no dependencies)
```

The resolved order would be: `dep-a`, `dep-c`, `dep-b`, `main-skill`. Every skill appears after all of its dependencies.

### Circular Dependency Detection

Circular dependencies are detected during loading and raise a `ValueError`:

```python
# skill-a depends on skill-b, skill-b depends on skill-a
try:
    skill = SkillLoader.load("skill-a", cwd=".")
except ValueError as e:
    print(e)
    # Circular dependency detected: 'skill-a' is already being loaded.
    # Chain: skill-a -> skill-b -> skill-a
```

Circular detection also works in `SkillLoader.resolve_all`:

```python
try:
    resolved = SkillLoader.resolve_all([skill_with_circular_deps])
except ValueError as e:
    print(e)
    # Circular dependency detected involving 'skill-name'
```

### Deduplication

If multiple skills share a common dependency, it is included only once in the resolved list. The topological sort tracks visited skills by name and skips duplicates.

---

## Creating Your Own Skills

### Step 1: Choose a Location

Decide whether the skill is project-specific or shared across projects:

- **Project-level:** Create the skill in `<your-project>/.agents/skills/<skill-name>/`
- **User-level:** Create the skill in `~/.agents/skills/<skill-name>/`

### Step 2: Create the Directory

```bash
mkdir -p .agents/skills/my-custom-skill
```

### Step 3: Write the SKILL.md File

Create `.agents/skills/my-custom-skill/SKILL.md`:

```markdown
---
name: my-custom-skill
description: Enforces team coding standards and best practices
license: MIT
metadata:
  author: your-name
  version: "1.0"
  tags:
    - code-quality
    - standards
---

# Coding Standards Skill

When reviewing or writing code, follow these standards:

## Naming Conventions

- Use snake_case for Python functions and variables.
- Use PascalCase for class names.
- Use UPPER_SNAKE_CASE for constants.

## Documentation

- Every public function must have a docstring.
- Every module must have a module-level docstring.

## Error Handling

- Never use bare `except:` clauses.
- Always specify the exception type.
- Log errors before re-raising.
```

### Step 4: Add Helper Scripts (Optional)

If your skill references external scripts:

```bash
mkdir -p .agents/skills/my-custom-skill/scripts
```

Create `.agents/skills/my-custom-skill/scripts/lint.sh`:

```bash
#!/bin/bash
# Run linting checks
ruff check "$@"
```

Reference the script in your `SKILL.md`:

```markdown
## Linting

To check code quality, run the linting script located at
`scripts/lint.sh` in this skill's directory.
```

### Step 5: Add Dependencies (Optional)

If your skill builds on other skills, declare them:

```yaml
---
name: my-custom-skill
description: Enforces team coding standards
dependencies:
  - base-formatting
---
```

Make sure the dependency skills exist in the standard locations.

### Step 6: Test the Skill

Verify the skill loads correctly:

```python
from acp_agent_framework import SkillLoader

# Test loading
skill = SkillLoader.load("my-custom-skill", cwd=".")
print(f"Name: {skill.name}")
print(f"Description: {skill.description}")
print(f"Instruction length: {len(skill.instruction)} chars")
print(f"Dependencies: {[d.name for d in skill.dependencies]}")
```

### Step 7: Use with an Agent

```python
from acp_agent_framework import Agent, Context

agent = Agent(
    name="standards-enforcer",
    backend="claude",
    instruction="Review the provided code and apply all loaded skill standards.",
    skills=["my-custom-skill"],
)

ctx = Context(session_id="review-1", cwd=".")
ctx.set_input("Review this function:\n\ndef foo(x):\n  return x+1")
```

---

## Discovering Skills Programmatically

Use `SkillLoader.discover` to find all available skills without knowing their names in advance.

### List All Available Skills

```python
from acp_agent_framework import SkillLoader

skills = SkillLoader.discover(".")
for name, skill in skills.items():
    print(f"{name}: {skill.description}")
    print(f"  Location: {skill.path}")
    if skill.metadata:
        print(f"  Metadata: {skill.metadata}")
    print()
```

### Filter Skills by Metadata

```python
from acp_agent_framework import SkillLoader

skills = SkillLoader.discover(".")

# Find skills by a specific author
author_skills = {
    name: skill for name, skill in skills.items()
    if skill.metadata.get("metadata", {}).get("author") == "your-team"
}

# Find skills with a specific license
mit_skills = {
    name: skill for name, skill in skills.items()
    if skill.metadata.get("license") == "MIT"
}
```

### Build a Skill Catalog

```python
from acp_agent_framework import SkillLoader

def print_catalog(cwd: str) -> None:
    """Print a formatted catalog of all available skills."""
    skills = SkillLoader.discover(cwd)

    if not skills:
        print("No skills found.")
        return

    print(f"Found {len(skills)} skill(s):\n")
    for name, skill in sorted(skills.items()):
        desc = skill.description or "(no description)"
        print(f"  {name}")
        print(f"    Description: {desc}")
        print(f"    Path: {skill.path}")
        meta = skill.metadata.get("metadata", {})
        if meta:
            version = meta.get("version", "unknown")
            author = meta.get("author", "unknown")
            print(f"    Version: {version}, Author: {author}")
        print()

print_catalog(".")
```

### Dynamically Select Skills

```python
import asyncio
from acp_agent_framework import Agent, Context, SkillLoader

def select_skills(cwd: str, required_tags: list[str]) -> list[str]:
    """Select skills that have any of the required tags."""
    skills = SkillLoader.discover(cwd)
    selected = []
    for name, skill in skills.items():
        tags = skill.metadata.get("metadata", {}).get("tags", [])
        if any(tag in tags for tag in required_tags):
            selected.append(name)
    return selected

async def main():
    cwd = "."
    skill_names = select_skills(cwd, required_tags=["code-quality"])

    agent = Agent(
        name="quality-agent",
        backend="claude",
        instruction="Apply all loaded quality skills to the code.",
        skills=skill_names,
    )

    ctx = Context(session_id="quality-1", cwd=cwd)
    ctx.set_input("Review this codebase for quality issues.")

    async for event in agent.run(ctx):
        print(event.content)

asyncio.run(main())
```

---

## Reference

### Imports

```python
# Top-level imports
from acp_agent_framework import Skill, SkillLoader

# Direct module imports
from acp_agent_framework.skills import Skill, SkillLoader
from acp_agent_framework.skills.skill import Skill
from acp_agent_framework.skills.loader import SkillLoader
```

### Standard Skill Directories

| Directory | Scope | Priority |
|-----------|-------|----------|
| `<cwd>/.agents/skills/` | Project | Higher (overrides user) |
| `~/.agents/skills/` | User | Lower |

### Exceptions

| Exception | Raised By | Cause |
|-----------|-----------|-------|
| `FileNotFoundError` | `SkillLoader.load` | Skill directory or `SKILL.md` not found in any standard location. |
| `ValueError` | `SkillLoader.load`, `SkillLoader.resolve_all` | Circular dependency detected in the skill graph. |

### agentskills.io Compatibility

Skills created for the ACP Agent Framework follow the agentskills.io standard and are compatible with any agent that supports the standard. Conversely, skills created for other agents (Claude Code, Cursor, Windsurf, and others) can be used with the ACP Agent Framework without modification, as long as they follow the `SKILL.md` convention with YAML frontmatter.
