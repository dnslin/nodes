"""Launchers preserve arguments, process exit status, and virtual-display setup."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def launcher(tmp_path):
    script = tmp_path / "start.sh"
    shutil.copyfile(ROOT / "start.sh", script)
    script.chmod(0o755)
    python = tmp_path / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 23\n')
    python.chmod(0o755)
    tools = tmp_path / "tools"
    tools.mkdir()
    uname = tools / "uname"
    uname.write_text("#!/bin/sh\necho Linux\n")
    uname.chmod(0o755)
    return script, tools


def test_linux_launcher_with_display_forwards_arguments_and_failure(launcher):
    script, tools = launcher
    result = subprocess.run(
        [str(script), "--count", "2", "--hide-browser"],
        env={**os.environ, "DISPLAY": ":99", "PATH": f"{tools}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 23
    assert result.stdout.splitlines() == [
        "proxyscrape_register.py",
        "--count",
        "2",
        "--hide-browser",
    ]


def test_linux_launcher_without_display_uses_xvfb_and_preserves_failure(launcher):
    script, tools = launcher
    xvfb = tools / "xvfb-run"
    xvfb.write_text('#!/bin/sh\nprintf "virtual-display\\n"\nshift 3\nexec "$@"\n')
    xvfb.chmod(0o755)
    environment = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}"}
    environment.pop("DISPLAY", None)
    result = subprocess.run(
        [str(script), "--count", "3"],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 23
    assert result.stdout.splitlines() == [
        "virtual-display",
        "proxyscrape_register.py",
        "--count",
        "3",
    ]


@pytest.fixture
def docker_launcher(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    script = project / "docker-run.sh"
    shutil.copyfile(ROOT / "docker-run.sh", script)
    script.chmod(0o755)
    tools = tmp_path / "tools"
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        "with open(os.environ['DOCKER_CALLS'], 'a') as log:\n"
        "    log.write(json.dumps(args) + '\\n')\n"
        "if args[0] == 'compose':\n"
        "    raise SystemExit(int(os.environ.get('RUN_EXIT', '0')))\n"
        "if args[0] == 'cp':\n"
        "    if os.environ.get('COPY_FAIL') == '1':\n"
        "        raise SystemExit(1)\n"
        "    dest = pathlib.Path(args[2])\n"
        "    dest.mkdir()\n"
        "    if args[1].endswith('/node'):\n"
        "        (dest / 'proxies_test.txt').write_text('http://user:pass@127.0.0.1:80\\n')\n"
        "    else:\n"
        "        (dest / 'accounts_test.jsonl').write_text('{}\\n')\n"
    )
    docker.chmod(0o755)
    calls = tmp_path / "calls.jsonl"
    temp = tmp_path / "temp"
    temp.mkdir()
    environment = {
        **os.environ,
        "PATH": f"{tools}:{os.environ['PATH']}",
        "DOCKER_CALLS": str(calls),
        "TMPDIR": str(temp),
    }
    return script, project, environment, calls, temp


@pytest.mark.parametrize("exit_code", [0, 1])
def test_docker_launcher_copies_outputs_before_removing_container(docker_launcher, exit_code):
    script, project, environment, calls_file, temp = docker_launcher
    result = subprocess.run(
        [str(script), "--resume", "saved@example.org"],
        cwd=project.parent,
        env={**environment, "RUN_EXIT": str(exit_code)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == exit_code, result.stderr
    assert (project / "node/proxies_test.txt").read_text() == "http://user:pass@127.0.0.1:80\n"
    assert (project / "account/accounts_test.jsonl").read_text() == "{}\n"
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    run, account_copy, node_copy, remove = calls
    assert run[:5] == ["compose", "run", "--no-deps", "--name", remove[1]]
    assert run[5:] == ["nodes", "--resume", "saved@example.org"]
    assert "--rm" not in run
    assert account_copy[1] == f"{remove[1]}:/app/account"
    assert node_copy[1] == f"{remove[1]}:/app/node"
    assert remove[0] == "rm"
    assert str(project / "node/") in result.stdout
    assert not list(temp.iterdir())


def test_docker_launcher_keeps_container_when_copy_fails(docker_launcher):
    script, project, environment, calls_file, temp = docker_launcher
    result = subprocess.run(
        [str(script), "--count", "1"],
        env={**environment, "COPY_FAIL": "1"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert not any(call[0] == "rm" for call in calls)
    assert "docker cp" in result.stderr
    assert not list((project / "node").iterdir())
    # 保留中途复制的输出，方便用户在失败后继续取出。
    assert list(temp.iterdir())
