"""Skill loader - discovers and parses SKILL.md files from standard directories."""
import re
from pathlib import Path
from typing import Any

from acp_agent_framework.skills.skill import Skill

# Standard skill directories per agentskills.io spec
_SKILL_DIRS = [
    ".agents/skills",  # project-level (cross-client)
]

_USER_SKILL_DIR = Path.home() / ".agents" / "skills"


def _parse_skill_md(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file into frontmatter dict and markdown body."""
    text = path.read_text(encoding="utf-8")

    # Check for YAML frontmatter (--- delimited)
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", text, re.DOTALL)
    if not match:
        # No frontmatter, entire file is the instruction
        return {}, text.strip()

    frontmatter_text = match.group(1)
    body = match.group(2).strip()

    try:
        import yaml
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except ImportError:
        # Fallback: basic key-value parsing if PyYAML not installed
        frontmatter = {}
        for line in frontmatter_text.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                frontmatter[key.strip()] = value.strip()

    return frontmatter, body


class SkillLoader:
    """Discovers and loads skills from standard filesystem locations."""

    @staticmethod
    def _validate_skill_name(name: str) -> None:
        """Reject skill names that could escape the skill directory."""
        if not name or "/" in name or "\\" in name or ".." in name or name in (".", ""):
            raise ValueError(
                f"Invalid skill name: {name!r}. "
                "Skill names must be single path components without separators or '..'."
            )

    @staticmethod
    def _find_skill_path(name: str, cwd: str) -> Path | None:
        """Find a skill by name, checking project-level then user-level."""
        SkillLoader._validate_skill_name(name)
        cwd_path = Path(cwd)

        # Project-level directories (higher priority)
        for skill_dir in _SKILL_DIRS:
            skill_path = cwd_path / skill_dir / name / "SKILL.md"
            skill_root_resolved = (cwd_path / skill_dir).resolve()
            if skill_path.resolve().is_file() and str(skill_path.resolve()).startswith(str(skill_root_resolved)):
                return skill_path

        # User-level directory (lower priority)
        user_path = _USER_SKILL_DIR / name / "SKILL.md"
        user_root_resolved = _USER_SKILL_DIR.resolve()
        if user_path.resolve().is_file() and str(user_path.resolve()).startswith(str(user_root_resolved)):
            return user_path

        return None

    @staticmethod
    def load(name: str, cwd: str, _loading: set[str] | None = None) -> Skill:
        """Load a skill by name from standard directories.

        Recursively loads dependencies declared in frontmatter.
        Raises FileNotFoundError if the skill is not found.
        Raises ValueError on circular dependencies.
        """
        if _loading is None:
            _loading = set()

        if name in _loading:
            raise ValueError(
                f"Circular dependency detected: '{name}' is already being loaded. "
                f"Chain: {' -> '.join(_loading)} -> {name}"
            )

        _loading.add(name)

        skill_path = SkillLoader._find_skill_path(name, cwd)
        if skill_path is None:
            search_dirs = [
                str(Path(cwd) / d / name) for d in _SKILL_DIRS
            ] + [str(_USER_SKILL_DIR / name)]
            raise FileNotFoundError(
                f"Skill '{name}' not found. Searched:\n"
                + "\n".join(f"  - {d}/SKILL.md" for d in search_dirs)
            )

        frontmatter, body = _parse_skill_md(skill_path)

        # Extract dependency names from frontmatter
        dep_names: list[str] = frontmatter.get("dependencies", []) or []
        if isinstance(dep_names, str):
            dep_names = [dep_names]

        # Recursively load dependencies
        loaded_deps: list[Skill] = []
        for dep_name in dep_names:
            loaded_deps.append(SkillLoader.load(dep_name, cwd, _loading=set(_loading)))

        return Skill(
            name=frontmatter.get("name", name),
            description=frontmatter.get("description", ""),
            instruction=body,
            path=skill_path.parent,
            metadata={
                k: v for k, v in frontmatter.items()
                if k not in ("name", "description", "dependencies")
            },
            dependencies=loaded_deps,
        )

    @staticmethod
    def resolve_all(skills: list[Skill]) -> list[Skill]:
        """Return a flat list of skills in topological order (dependencies first).

        Raises ValueError on circular dependencies.
        """
        resolved: list[Skill] = []
        seen: set[str] = set()
        visiting: set[str] = set()

        def _visit(skill: Skill) -> None:
            if skill.name in seen:
                return
            if skill.name in visiting:
                raise ValueError(
                    f"Circular dependency detected involving '{skill.name}'"
                )
            visiting.add(skill.name)
            for dep in skill.dependencies:
                _visit(dep)
            visiting.discard(skill.name)
            seen.add(skill.name)
            resolved.append(skill)

        for skill in skills:
            _visit(skill)

        return resolved

    @staticmethod
    def discover(cwd: str) -> dict[str, Skill]:
        """Discover all available skills from standard directories.

        Returns a dict mapping skill name to Skill object.
        Project-level skills override user-level on name collision.
        """
        skills: dict[str, Skill] = {}

        # User-level first (lower priority, will be overridden)
        if _USER_SKILL_DIR.is_dir():
            for skill_dir in sorted(_USER_SKILL_DIR.iterdir()):
                skill_md = skill_dir / "SKILL.md"
                if skill_dir.is_dir() and skill_md.is_file():
                    frontmatter, body = _parse_skill_md(skill_md)
                    skill_name = frontmatter.get("name", skill_dir.name)
                    skills[skill_dir.name] = Skill(
                        name=skill_name,
                        description=frontmatter.get("description", ""),
                        instruction=body,
                        path=skill_dir,
                        metadata={
                            k: v for k, v in frontmatter.items()
                            if k not in ("name", "description")
                        },
                    )

        # Project-level (higher priority, overrides user-level)
        cwd_path = Path(cwd)
        for skill_dir_name in _SKILL_DIRS:
            skills_root = cwd_path / skill_dir_name
            if skills_root.is_dir():
                for skill_dir in sorted(skills_root.iterdir()):
                    skill_md = skill_dir / "SKILL.md"
                    if skill_dir.is_dir() and skill_md.is_file():
                        frontmatter, body = _parse_skill_md(skill_md)
                        skill_name = frontmatter.get("name", skill_dir.name)
                        skills[skill_dir.name] = Skill(
                            name=skill_name,
                            description=frontmatter.get("description", ""),
                            instruction=body,
                            path=skill_dir,
                            metadata={
                                k: v for k, v in frontmatter.items()
                                if k not in ("name", "description")
                            },
                        )

        return skills
