"""CLI tool for ACP Agent Framework."""
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click


@click.group()
def main():
    """ACP Agent Framework CLI."""
    pass


@main.command()
@click.argument("module_path")
@click.option("--transport", "-t", default="acp", type=click.Choice(["acp", "http"]))
@click.option("--host", default="0.0.0.0")
@click.option("--port", "-p", default=8000, type=int)
def run(module_path: str, transport: str, host: str, port: int):
    """Run an agent. MODULE_PATH is 'module:attribute' (e.g. 'my_agent:agent')."""
    module_name, _, attr_name = module_path.partition(":")
    if not attr_name:
        attr_name = "agent"

    try:
        module = importlib.import_module(module_name)
    except ImportError as e:
        click.echo(f"Error: Could not import module '{module_name}': {e}", err=True)
        sys.exit(1)

    agent = getattr(module, attr_name, None)
    if agent is None:
        click.echo(f"Error: Module '{module_name}' has no attribute '{attr_name}'", err=True)
        sys.exit(1)

    from acp_agent_framework.server.serve import serve
    serve(agent, transport=transport, host=host, port=port)


@main.command()
@click.argument("name")
def init(name: str):
    """Scaffold a new agent project."""
    os.makedirs(name, exist_ok=True)
    agent_file = os.path.join(name, "agent.py")
    if not os.path.exists(agent_file):
        with open(agent_file, "w") as f:
            f.write(f'''"""Example agent created with acp-agent init."""
from acp_agent_framework.agents import Agent

agent = Agent(
    name="{name}",
    backend="claude",
    instruction="You are a helpful assistant.",
)

if __name__ == "__main__":
    from acp_agent_framework.server.serve import serve
    serve(agent)
''')
    click.echo(f"Created agent project: {name}/")
    click.echo(f"  {agent_file}")
    click.echo(f"\nRun with: acp-agent run {name}.agent:agent")


# ---------------------------------------------------------------------------
# skill command group
# ---------------------------------------------------------------------------

_USER_SKILLS_DIR = Path.home() / ".agents" / "skills"
_PROJECT_SKILLS_DIR = Path(".agents") / "skills"


@main.group()
def skill():
    """Manage agent skills (install, list, search, remove, info)."""
    pass


@skill.command("install")
@click.argument("source")
@click.option(
    "--project", "level", flag_value="project", default=False,
    help="Install to project-level .agents/skills/ instead of user-level.",
)
def skill_install(source: str, level: str):
    """Install a skill from a GitHub URL or local path."""
    is_project = level == "project"
    target_root = Path.cwd() / _PROJECT_SKILLS_DIR if is_project else _USER_SKILLS_DIR

    if _is_github_url(source):
        _install_from_github(source, target_root)
    else:
        _install_from_local(source, target_root)


def _is_github_url(source: str) -> bool:
    """Check if the source looks like a GitHub URL."""
    return source.startswith(("github.com/", "https://github.com/"))


def _install_from_github(source: str, target_root: Path) -> None:
    """Clone a GitHub repo (or subfolder) and install the skill."""
    # Normalise URL
    url = source.removeprefix("https://")  # now: github.com/user/repo[/sub/path]
    parts = url.split("/")
    if len(parts) < 3:
        click.echo("Error: Invalid GitHub URL. Expected github.com/user/repo", err=True)
        sys.exit(1)

    user, repo = parts[1], parts[2]
    subfolder = "/".join(parts[3:]) if len(parts) > 3 else ""
    clone_url = f"https://github.com/{user}/{repo}.git"
    skill_name = parts[-1]  # last segment as name

    # Check git is available
    if shutil.which("git") is None:
        click.echo(
            "Error: git is not installed. Install git to clone from GitHub.\n"
            "  macOS: xcode-select --install\n"
            "  Linux: sudo apt install git",
            err=True,
        )
        sys.exit(1)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, tmpdir],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            click.echo(f"Error: git clone failed:\n{result.stderr.strip()}", err=True)
            sys.exit(1)

        src_dir = Path(tmpdir) / subfolder if subfolder else Path(tmpdir)
        if not src_dir.is_dir():
            click.echo(f"Error: Subfolder '{subfolder}' not found in repo.", err=True)
            sys.exit(1)

        # Validate SKILL.md
        if not (src_dir / "SKILL.md").is_file():
            click.echo(
                f"Error: No SKILL.md found in {source}. "
                "A valid skill must contain a SKILL.md file.",
                err=True,
            )
            sys.exit(1)

        dest = target_root / skill_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src_dir, dest, ignore=shutil.ignore_patterns(".git"))

    click.echo(f"Installed skill '{skill_name}' to {dest}")


def _install_from_local(source: str, target_root: Path) -> None:
    """Copy a local directory as a skill."""
    src = Path(source).resolve()
    if not src.is_dir():
        click.echo(f"Error: '{source}' is not a directory.", err=True)
        sys.exit(1)

    if not (src / "SKILL.md").is_file():
        click.echo(
            f"Error: No SKILL.md found in {source}. "
            "A valid skill must contain a SKILL.md file.",
            err=True,
        )
        sys.exit(1)

    skill_name = src.name
    dest = target_root / skill_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    click.echo(f"Installed skill '{skill_name}' to {dest}")


@skill.command("list")
def skill_list():
    """List all installed skills (user and project level)."""
    from acp_agent_framework.skills.loader import SkillLoader

    skills = SkillLoader.discover(str(Path.cwd()))

    if not skills:
        click.echo("No skills installed.")
        return

    for key, s in sorted(skills.items()):
        # Determine level based on path
        path_str = str(s.path)
        if str(_USER_SKILLS_DIR) in path_str:
            level = "user"
        else:
            level = "project"
        desc = s.description or "(no description)"
        click.echo(f"  {s.name:<20} {desc:<40} [{level}] {s.path}")


@skill.command("search")
@click.argument("query")
def skill_search(query: str):
    """Search installed skills by name or description."""
    from acp_agent_framework.skills.loader import SkillLoader

    skills = SkillLoader.discover(str(Path.cwd()))
    query_lower = query.lower()
    matches = [
        s for s in skills.values()
        if query_lower in s.name.lower() or query_lower in s.description.lower()
    ]

    if not matches:
        click.echo(f"No skills matching '{query}'.")
        return

    for s in matches:
        desc = s.description or "(no description)"
        click.echo(f"  {s.name:<20} {desc}")


@skill.command("remove")
@click.argument("name")
@click.option("--project", "level", flag_value="project", help="Remove from project level.")
@click.option("--user", "level", flag_value="user", default=True, help="Remove from user level (default).")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation.")
def skill_remove(name: str, level: str, yes: bool):
    """Remove an installed skill by name."""
    if level == "project":
        skill_dir = Path.cwd() / _PROJECT_SKILLS_DIR / name
    else:
        skill_dir = _USER_SKILLS_DIR / name

    if not skill_dir.is_dir():
        click.echo(f"Error: Skill '{name}' not found at {skill_dir}", err=True)
        sys.exit(1)

    if not yes:
        click.confirm(f"Remove skill '{name}' from {skill_dir}?", abort=True)

    shutil.rmtree(skill_dir)
    click.echo(f"Removed skill '{name}' from {skill_dir}")


@skill.command("info")
@click.argument("name")
def skill_info(name: str):
    """Show detailed info about an installed skill."""
    from acp_agent_framework.skills.loader import SkillLoader

    skills = SkillLoader.discover(str(Path.cwd()))

    # Search by directory key or by display name
    s = skills.get(name)
    if s is None:
        for sk in skills.values():
            if sk.name == name:
                s = sk
                break

    if s is None:
        click.echo(f"Error: Skill '{name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"Name:         {s.name}")
    click.echo(f"Description:  {s.description or '(none)'}")
    click.echo(f"Path:         {s.path}")

    preview = s.instruction[:200]
    if len(s.instruction) > 200:
        preview += "..."
    click.echo(f"Instruction:  {preview}")

    if s.metadata:
        click.echo(f"Metadata:     {s.metadata}")

    if s.dependencies:
        dep_names = [d.name for d in s.dependencies]
        click.echo(f"Dependencies: {', '.join(dep_names)}")
