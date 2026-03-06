import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from acp_agent_framework.skills.loader import SkillLoader, _parse_skill_md
from acp_agent_framework.agents.agent import Agent
from acp_agent_framework.context import Context


def _create_skill(base_dir, name, content):
    """Helper to create a skill directory with SKILL.md."""
    skill_dir = Path(base_dir) / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content)
    return skill_dir


SAMPLE_SKILL_MD = """---
name: test-skill
description: A test skill for unit testing
license: Apache-2.0
metadata:
  author: test
  version: "1.0"
---

# Test Skill Instructions

You are a test skill. Follow these steps:

1. Do step one
2. Do step two
3. Return results
"""

MINIMAL_SKILL_MD = """# Just Instructions

No frontmatter here, just plain markdown instructions.
"""


def test_parse_skill_md_with_frontmatter():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SAMPLE_SKILL_MD)
        f.flush()
        frontmatter, body = _parse_skill_md(Path(f.name))
    os.unlink(f.name)
    assert frontmatter["name"] == "test-skill"
    assert frontmatter["description"] == "A test skill for unit testing"
    assert "# Test Skill Instructions" in body
    assert "Do step one" in body


def test_parse_skill_md_without_frontmatter():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(MINIMAL_SKILL_MD)
        f.flush()
        frontmatter, body = _parse_skill_md(Path(f.name))
    os.unlink(f.name)
    assert frontmatter == {}
    assert "Just Instructions" in body


def test_skill_loader_load_from_project():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "my-skill", SAMPLE_SKILL_MD)
        skill = SkillLoader.load("my-skill", tmpdir)
        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing"
        assert "Do step one" in skill.instruction
        assert skill.path == skills_dir / "my-skill"
        assert skill.metadata.get("license") == "Apache-2.0"
        assert skill.metadata["metadata"]["author"] == "test"


def test_skill_loader_load_missing_raises():
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(FileNotFoundError, match="not found"):
            SkillLoader.load("nonexistent-skill", tmpdir)


def test_skill_loader_discover():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "skill-a", SAMPLE_SKILL_MD)
        _create_skill(skills_dir, "skill-b", MINIMAL_SKILL_MD)
        skills = SkillLoader.discover(tmpdir)
        assert "skill-a" in skills
        assert "skill-b" in skills
        assert skills["skill-a"].name == "test-skill"
        assert "Just Instructions" in skills["skill-b"].instruction


def test_skill_loader_project_overrides_user(tmp_path, monkeypatch):
    # Create user-level skill
    user_skills = tmp_path / "user_home" / ".agents" / "skills"
    _create_skill(user_skills, "shared", "---\nname: user-version\n---\nUser instructions")

    # Create project-level skill with same name
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    project_skills = project_dir / ".agents" / "skills"
    _create_skill(project_skills, "shared", "---\nname: project-version\n---\nProject instructions")

    # Monkeypatch user skill dir
    import acp_agent_framework.skills.loader as loader_mod
    monkeypatch.setattr(loader_mod, "_USER_SKILL_DIR", user_skills)

    skills = SkillLoader.discover(str(project_dir))
    assert skills["shared"].name == "project-version"
    assert "Project instructions" in skills["shared"].instruction


@pytest.mark.asyncio
async def test_agent_with_skills():
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "helper", "---\nname: helper\n---\nYou are a helpful assistant skill.")

        agent = Agent(
            name="test",
            backend="claude",
            instruction="Base instruction.",
            skills=["helper"],
        )
        ctx = Context(session_id="s1", cwd=tmpdir)
        ctx.set_input("Hello")

        with patch.object(agent, "_get_backend") as mock_get:
            mock_backend = AsyncMock()
            mock_backend.start = AsyncMock()
            mock_backend.new_session = AsyncMock(return_value="sess-123")
            mock_backend.prompt = AsyncMock(return_value="Response")
            mock_backend.stop = AsyncMock()
            mock_get.return_value = mock_backend

            async for _ in agent.run(ctx):
                pass

            # Verify the prompt included skill instructions
            prompt_call = mock_backend.prompt.call_args
            sent_text = prompt_call[0][1]  # second positional arg is the text
            assert "helpful assistant skill" in sent_text
            assert "Base instruction" in sent_text


SKILL_WITH_DEPS_MD = """---
name: main-skill
description: A skill with dependencies
dependencies: [dep-a, dep-b]
---

# Main Skill

I depend on dep-a and dep-b.
"""

DEP_A_MD = """---
name: dep-a
description: Dependency A
---

# Dep A Instructions

I am dependency A.
"""

DEP_B_MD = """---
name: dep-b
description: Dependency B
dependencies: [dep-c]
---

# Dep B Instructions

I am dependency B and depend on dep-c.
"""

DEP_C_MD = """---
name: dep-c
description: Dependency C
---

# Dep C Instructions

I am dependency C (leaf).
"""

CIRCULAR_A_MD = """---
name: circ-a
dependencies: [circ-b]
---
Circular A
"""

CIRCULAR_B_MD = """---
name: circ-b
dependencies: [circ-a]
---
Circular B
"""


def test_parse_skill_md_with_dependencies():
    """Dependencies field is extracted from frontmatter."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(SKILL_WITH_DEPS_MD)
        f.flush()
        frontmatter, body = _parse_skill_md(Path(f.name))
    os.unlink(f.name)
    assert frontmatter["dependencies"] == ["dep-a", "dep-b"]
    assert "Main Skill" in body


def test_skill_loader_load_with_dependencies():
    """Loading a skill recursively loads its dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "main-skill", SKILL_WITH_DEPS_MD)
        _create_skill(skills_dir, "dep-a", DEP_A_MD)
        _create_skill(skills_dir, "dep-b", DEP_B_MD)
        _create_skill(skills_dir, "dep-c", DEP_C_MD)

        skill = SkillLoader.load("main-skill", tmpdir)
        assert skill.name == "main-skill"
        assert len(skill.dependencies) == 2
        assert skill.dependencies[0].name == "dep-a"
        assert skill.dependencies[1].name == "dep-b"
        # dep-b has a transitive dependency on dep-c
        assert len(skill.dependencies[1].dependencies) == 1
        assert skill.dependencies[1].dependencies[0].name == "dep-c"


def test_circular_dependency_detection():
    """Circular dependencies raise ValueError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "circ-a", CIRCULAR_A_MD)
        _create_skill(skills_dir, "circ-b", CIRCULAR_B_MD)

        with pytest.raises(ValueError, match="Circular dependency"):
            SkillLoader.load("circ-a", tmpdir)


def test_resolve_all_topological_order():
    """resolve_all returns skills in dependency-first order."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "main-skill", SKILL_WITH_DEPS_MD)
        _create_skill(skills_dir, "dep-a", DEP_A_MD)
        _create_skill(skills_dir, "dep-b", DEP_B_MD)
        _create_skill(skills_dir, "dep-c", DEP_C_MD)

        skill = SkillLoader.load("main-skill", tmpdir)
        resolved = SkillLoader.resolve_all([skill])
        names = [s.name for s in resolved]
        # Dependencies should come before the skill that depends on them
        assert names.index("dep-a") < names.index("main-skill")
        assert names.index("dep-b") < names.index("main-skill")
        assert names.index("dep-c") < names.index("dep-b")


@pytest.mark.asyncio
async def test_agent_with_skill_dependencies():
    """Agent resolves skill instructions including dependencies."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skills_dir = Path(tmpdir) / ".agents" / "skills"
        _create_skill(skills_dir, "main-skill", SKILL_WITH_DEPS_MD)
        _create_skill(skills_dir, "dep-a", DEP_A_MD)
        _create_skill(skills_dir, "dep-b", DEP_B_MD)
        _create_skill(skills_dir, "dep-c", DEP_C_MD)

        agent = Agent(
            name="test",
            backend="claude",
            instruction="Base instruction.",
            skills=["main-skill"],
        )
        ctx = Context(session_id="s1", cwd=tmpdir)
        ctx.set_input("Hello")

        with patch.object(agent, "_get_backend") as mock_get:
            mock_backend = AsyncMock()
            mock_backend.start = AsyncMock()
            mock_backend.new_session = AsyncMock(return_value="sess-123")
            mock_backend.prompt = AsyncMock(return_value="Response")
            mock_backend.stop = AsyncMock()
            mock_get.return_value = mock_backend

            async for _ in agent.run(ctx):
                pass

            prompt_call = mock_backend.prompt.call_args
            sent_text = prompt_call[0][1]
            # All dependency instructions should be included
            assert "dependency A" in sent_text
            assert "dependency B" in sent_text
            assert "dependency C" in sent_text
            assert "Main Skill" in sent_text
            assert "Base instruction" in sent_text


@pytest.mark.asyncio
async def test_agent_with_missing_skill():
    with tempfile.TemporaryDirectory() as tmpdir:
        agent = Agent(
            name="test",
            backend="claude",
            instruction="Base.",
            skills=["nonexistent"],
        )
        ctx = Context(session_id="s1", cwd=tmpdir)
        ctx.set_input("Hello")

        with patch.object(agent, "_get_backend") as mock_get:
            mock_backend = AsyncMock()
            mock_backend.start = AsyncMock()
            mock_backend.new_session = AsyncMock(return_value="sess-123")
            mock_backend.prompt = AsyncMock(return_value="Response")
            mock_backend.stop = AsyncMock()
            mock_get.return_value = mock_backend

            with pytest.raises(FileNotFoundError, match="not found"):
                async for _ in agent.run(ctx):
                    pass


@pytest.mark.parametrize("bad_name", [
    "../escape",
    "../../etc",
    "foo/bar",
    "foo\\bar",
    "..",
    "",
])
def test_skill_name_path_traversal_rejected(bad_name):
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="Invalid skill name"):
            SkillLoader.load(bad_name, tmpdir)
