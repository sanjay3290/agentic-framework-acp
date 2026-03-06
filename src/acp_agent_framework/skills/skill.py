"""Skill data class representing a parsed SKILL.md file."""
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
