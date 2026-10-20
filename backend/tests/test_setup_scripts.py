"""Run copied Windows entry points with fake installers/seeder; no real environment writes."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows batch entry points")


@pytest.fixture
def copied_setup(tmp_path):
    workspace = tmp_path / "workspace with spaces"
    backend = workspace / "backend"
    frontend = workspace / "frontend"
    scripts = backend / "venv" / "Scripts"
    scripts.mkdir(parents=True)
    frontend.mkdir()
    for name in ("setup.bat", "seed.bat"):
        shutil.copyfile(ROOT / name, workspace / name)
    (scripts / "activate.bat").write_text("@exit /b 0\n")
    (backend / "requirements.txt").write_text("")
    (backend / ".env.example").write_text(
        "DATABASE_URL=example-only\nAPP_SECRET_KEY=change-me-to-a-secure-random-string\n"
        "JWT_SECRET_KEY=your-jwt-secret-key-here\n",
    )
    (frontend / ".env.development").write_text("VITE_API_URL=http://example.invalid\n")
    (backend / "seed.py").write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path('seed-invoked').write_text('fixture')\n"
        "pathlib.Path('seed-args').write_text(' '.join(sys.argv[1:]))\n"
        "sys.exit(int(os.environ.get('BV_TEST_SEED_EXIT', '0')))\n",
    )
    fake_bin = tmp_path / "commands"
    fake_bin.mkdir()
    (fake_bin / "npm.cmd").write_text("@exit /b %BV_TEST_INSTALL_EXIT%\n")
    # Intercept only dependency commands. All setup .env commands use actual Python.
    (fake_bin / "sitecustomize.py").write_text(
        "import os, sys\n"
        "install = '-m' in sys.orig_argv and any(x in sys.orig_argv for x in ('pip', 'venv'))\n"
        "if install or '-r' in sys.orig_argv:\n"
        "    os._exit(int(os.environ.get('BV_TEST_INSTALL_EXIT', '0')))\n",
    )
    env = {
        key: os.environ[key]
        for key in (
            "SystemRoot",
            "WINDIR",
            "TEMP",
            "TMP",
            "PATH",
            "PATHEXT",
            "COMSPEC",
            "USERPROFILE",
            "LOCALAPPDATA",
        )
        if key in os.environ
    }
    env.update(
        PATH=str(fake_bin)
        + os.pathsep
        + str(Path(sys.executable).parent)
        + os.pathsep
        + env["PATH"],
        PYTHONPATH=str(fake_bin),
        BV_TEST_INSTALL_EXIT="0",
        BV_TEST_SEED_EXIT="0",
    )
    return workspace, env


def run_script(workspace, env, name, answers=""):
    answer_file = workspace / "answers.txt"
    answer_file.write_text(answers)
    with answer_file.open() as stdin:
        return subprocess.run(
            ["cmd.exe", "/d", "/c", "call", str(workspace / name)],
            cwd=workspace,
            env=env,
            stdin=stdin,
            capture_output=True,
            text=True,
            timeout=30,
        )


@pytest.mark.parametrize("password", ["fixture_password", "fixture!p@ss:word/%&"])
def test_setup_configures_database_and_runs_seed(copied_setup, password):
    workspace, env = copied_setup
    result = run_script(
        workspace,
        env,
        "setup.bat",
        f"y\nfixture_user\n{password}\nlocalhost\n5439\nfixture_db\ny\n",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    configured = (workspace / "backend" / ".env").read_text()
    url = make_url(
        next(
            line.split("=", 1)[1]
            for line in configured.splitlines()
            if line.startswith("DATABASE_URL=")
        )
    )
    assert (url.username, url.password, url.host, url.port, url.database) == (
        "fixture_user",
        password,
        "localhost",
        5439,
        "fixture_db",
    )
    assert (workspace / "backend" / "seed-invoked").exists()


@pytest.mark.parametrize("name", ["setup.bat", "seed.bat"])
def test_entry_points_propagate_seed_failure_and_preserve_env(copied_setup, name):
    workspace, env = copied_setup
    for folder in ("backend", "frontend"):
        (workspace / folder / ".env").write_text("existing fixture config\n")
    env["BV_TEST_SEED_EXIT"] = "7"
    result = run_script(workspace, env, name, "y\n")
    assert result.returncode != 0, result.stdout
    assert "successfully" not in result.stdout and "Setup Complete" not in result.stdout
    for folder in ("backend", "frontend"):
        assert (workspace / folder / ".env").read_text() == "existing fixture config\n"


def test_setup_stops_on_dependency_failure(copied_setup):
    workspace, env = copied_setup
    (workspace / "backend" / ".env").write_text("existing fixture config\n")
    env["BV_TEST_INSTALL_EXIT"] = "9"
    result = run_script(workspace, env, "setup.bat", "y\n")
    assert result.returncode != 0, result.stdout
    assert not (workspace / "backend" / "seed-invoked").exists()
    assert "Setup Complete" not in result.stdout


@pytest.mark.parametrize("name", ["setup.bat", "seed.bat"])
def test_missing_seed_script_remains_an_error(copied_setup, name):
    workspace, env = copied_setup
    (workspace / "backend" / ".env").write_text("existing fixture config\n")
    (workspace / "backend" / "seed.py").unlink()
    result = run_script(workspace, env, name, "y\n")
    assert result.returncode != 0
    assert "[ERROR]" in result.stdout
    assert "Demo seeding skipped" not in result.stdout
    assert "Setup Complete" not in result.stdout


@pytest.mark.parametrize("name", ["setup.bat", "seed.bat"])
@pytest.mark.parametrize("answer", ["y\n", "n\n", "\n"])
def test_seed_reset_requires_yes_and_preserves_environment(copied_setup, name, answer):
    workspace, env = copied_setup
    for folder in ("backend", "frontend"):
        (workspace / folder / ".env").write_text("existing fixture config\n")
    result = run_script(workspace, env, name, answer)
    assert result.returncode == 0, result.stdout
    assert "deletes existing" in result.stdout
    assert "[ERROR]" not in result.stdout
    invoked = workspace / "backend" / "seed-invoked"
    assert invoked.exists() == (answer == "y\n")
    if invoked.exists():
        assert (workspace / "backend" / "seed-args").read_text() == "--reset-demo"
    assert ("Setup Complete" in result.stdout) == (name == "setup.bat")
    for folder in ("backend", "frontend"):
        assert (workspace / folder / ".env").read_text() == "existing fixture config\n"


@pytest.mark.parametrize("name", ["setup.sh", "seed.sh"])
@pytest.mark.parametrize("seed_exit", [0, 2, 7, 20])
@pytest.mark.parametrize("answer", [b"y\n", b"n\n", b"\n"])
def test_shell_entry_points_propagate_seed_result(copied_setup, name, seed_exit, answer):
    bash = Path("C:/Program Files/Git/bin/bash.exe")
    if not bash.exists():
        pytest.skip("Git Bash is unavailable")
    workspace, env = copied_setup
    shutil.copyfile(ROOT / name, workspace / name)
    for folder in ("backend", "frontend"):
        (workspace / folder / ".env").write_text("existing fixture config\n")
    activate = workspace / "backend" / "venv" / "bin" / "activate"
    activate.parent.mkdir()
    activate.write_text(
        'python() { printf "%s\\n" "$@" > seed-args; return "$BV_TEST_SEED_EXIT"; }\n'
        'python3() { if [ "$1" = "seed.py" ]; then python "$@"; else return 0; fi; }\n'
        "pip() { return 0; }\n"
        "npm() { return 0; }\n",
    )
    env["BV_TEST_SEED_EXIT"] = str(seed_exit)
    answers = workspace / "shell-answers.txt"
    answers.write_bytes(answer)  # Avoid Windows text-mode conversion to CRLF for Bash read.
    with answers.open("rb") as stdin:
        result = subprocess.run(
            [str(bash), "./" + name], cwd=workspace, env=env, stdin=stdin,
            capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
    expected = seed_exit if answer == b"y\n" else 0
    assert result.returncode == expected, result.stdout + result.stderr
    assert "deletes existing" in result.stdout
    seed_args = workspace / "backend" / "seed-args"
    assert seed_args.exists() == (answer == b"y\n")
    if seed_args.exists():
        assert seed_args.read_text().splitlines() == ["seed.py", "--reset-demo"]
    if expected:
        assert "successfully" not in result.stdout and "Setup Complete" not in result.stdout
    for folder in ("backend", "frontend"):
        assert (workspace / folder / ".env").read_text() == "existing fixture config\n"
