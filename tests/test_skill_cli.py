"""Tests for the skill marketplace CLI commands."""
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from acp_agent_framework.cli import main


def _create_skill(base_dir, name, description="A test skill", body="Do something."):
    """Helper: create a minimal skill directory with SKILL.md."""
    skill_dir = Path(base_dir) / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}\n"
    )
    return skill_dir


def test_skill_list():
    """List skills discovers user-level and project-level skills."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        user_skills = Path(tmpdir) / "user_skills"
        project_dir = Path(tmpdir) / "project"
        project_skills = project_dir / ".agents" / "skills"

        _create_skill(user_skills, "my-skill", description="User skill")
        _create_skill(project_skills, "proj-skill", description="Project skill")

        with patch(
            "acp_agent_framework.skills.loader._USER_SKILL_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli._USER_SKILLS_DIR", user_skills
        ):
            result = runner.invoke(main, ["skill", "list"], catch_exceptions=False)

        # Invoke with project cwd by patching Path.cwd
        with patch(
            "acp_agent_framework.skills.loader._USER_SKILL_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli._USER_SKILLS_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli.Path.cwd", return_value=project_dir
        ):
            result = runner.invoke(main, ["skill", "list"], catch_exceptions=False)

        assert result.exit_code == 0
        assert "proj-skill" in result.output


def test_skill_install_local():
    """Install a local skill copies it to the target directory."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a source skill
        src = _create_skill(Path(tmpdir) / "src", "local-skill", description="Local one")

        user_skills = Path(tmpdir) / "user_skills"

        with patch("acp_agent_framework.cli._USER_SKILLS_DIR", user_skills):
            result = runner.invoke(
                main, ["skill", "install", str(src)], catch_exceptions=False
            )

        assert result.exit_code == 0
        assert "Installed skill 'local-skill'" in result.output
        installed = user_skills / "local-skill" / "SKILL.md"
        assert installed.is_file()


def test_skill_install_validates_skill_md():
    """Install fails if the source has no SKILL.md."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Directory without SKILL.md
        bad_dir = Path(tmpdir) / "no-skill"
        bad_dir.mkdir()
        (bad_dir / "README.md").write_text("Not a skill")

        user_skills = Path(tmpdir) / "user_skills"

        with patch("acp_agent_framework.cli._USER_SKILLS_DIR", user_skills):
            result = runner.invoke(
                main, ["skill", "install", str(bad_dir)], catch_exceptions=False
            )

        assert result.exit_code != 0
        assert "No SKILL.md found" in result.output


def test_skill_remove():
    """Remove deletes an installed skill."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        user_skills = Path(tmpdir) / "user_skills"
        _create_skill(user_skills, "removable")

        with patch("acp_agent_framework.cli._USER_SKILLS_DIR", user_skills):
            result = runner.invoke(
                main, ["skill", "remove", "removable", "--yes"],
                catch_exceptions=False,
            )

        assert result.exit_code == 0
        assert "Removed skill 'removable'" in result.output
        assert not (user_skills / "removable").exists()


def test_skill_info():
    """Info displays skill details."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        user_skills = Path(tmpdir) / "user_skills"
        _create_skill(
            user_skills, "info-skill",
            description="Detailed skill",
            body="This is the instruction body for the skill.",
        )

        with patch(
            "acp_agent_framework.skills.loader._USER_SKILL_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli._USER_SKILLS_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli.Path.cwd",
            return_value=Path(tmpdir) / "nonexistent_project",
        ):
            result = runner.invoke(
                main, ["skill", "info", "info-skill"], catch_exceptions=False
            )

        assert result.exit_code == 0
        assert "info-skill" in result.output
        assert "Detailed skill" in result.output
        assert "instruction body" in result.output


def test_skill_search():
    """Search finds skills by name or description substring."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        user_skills = Path(tmpdir) / "user_skills"
        _create_skill(user_skills, "alpha-tool", description="Alpha helper")
        _create_skill(user_skills, "beta-util", description="Beta utility")

        with patch(
            "acp_agent_framework.skills.loader._USER_SKILL_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli._USER_SKILLS_DIR", user_skills
        ), patch(
            "acp_agent_framework.cli.Path.cwd",
            return_value=Path(tmpdir) / "nonexistent_project",
        ):
            # Search by name
            result = runner.invoke(
                main, ["skill", "search", "alpha"], catch_exceptions=False
            )
            assert result.exit_code == 0
            assert "alpha-tool" in result.output
            assert "beta" not in result.output

            # Search by description
            result = runner.invoke(
                main, ["skill", "search", "utility"], catch_exceptions=False
            )
            assert result.exit_code == 0
            assert "beta-util" in result.output

            # No match
            result = runner.invoke(
                main, ["skill", "search", "nonexistent"], catch_exceptions=False
            )
            assert result.exit_code == 0
            assert "No skills matching" in result.output
