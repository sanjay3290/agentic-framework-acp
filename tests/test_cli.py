import os
import tempfile
from click.testing import CliRunner
from acp_agent_framework.cli import main


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "ACP Agent Framework CLI" in result.output


def test_cli_init():
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        project_name = os.path.join(tmpdir, "my_agent")
        result = runner.invoke(main, ["init", project_name])
        assert result.exit_code == 0
        assert os.path.exists(os.path.join(project_name, "agent.py"))


def test_cli_run_missing_module():
    runner = CliRunner()
    result = runner.invoke(main, ["run", "nonexistent_module_xyz:agent"])
    assert result.exit_code != 0
    assert "Could not import" in result.output
