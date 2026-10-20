"""Docker output retrieval preserves commands, results and recoverable failures."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def docker_launcher(tmp_path):
    project = tmp_path / "project with spaces"
    project.mkdir()
    script = project / "scripts/run-docker.sh"
    script.parent.mkdir()
    shutil.copyfile(ROOT / "scripts/run-docker.sh", script)
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
        "    if os.environ.get('COPY_FAIL') == '1' or (\n"
        "        os.environ.get('COPY_FAIL') == 'node' and args[1].endswith('/node')\n"
        "    ):\n"
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


@pytest.mark.parametrize("exit_code", [0, 1, 23])
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
    assert run[5:] == ["nodes", "nodes", "--resume", "saved@example.org"]
    assert "--rm" not in run
    assert account_copy[1] == f"{remove[1]}:/app/account"
    assert node_copy[1] == f"{remove[1]}:/app/node"
    assert remove[0] == "rm"
    assert str(project / "node/") in result.stdout
    assert not list(temp.iterdir())


@pytest.mark.parametrize("failure", ["1", "node"])
def test_docker_launcher_keeps_container_when_copy_fails(docker_launcher, failure):
    script, project, environment, calls_file, temp = docker_launcher
    result = subprocess.run(
        [str(script), "--count", "1"],
        env={**environment, "COPY_FAIL": failure},
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


def test_docker_launcher_without_arguments_uses_compose_default_command(docker_launcher):
    script, project, environment, calls_file, _temp = docker_launcher
    result = subprocess.run(
        [str(script)],
        cwd=project.parent,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert calls[0][-1] == "nodes"
    assert len(calls[0]) == 6
    assert (project / "node/proxies_test.txt").is_file()


def test_local_copy_failure_also_preserves_container_and_downloaded_outputs(docker_launcher):
    script, project, environment, calls_file, temp = docker_launcher
    copy = Path(environment["PATH"].split(os.pathsep)[0]) / "cp"
    copy.write_text("#!/bin/sh\nexit 1\n")
    copy.chmod(0o755)
    result = subprocess.run(
        [str(script)],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert [call[0] for call in calls] == ["compose", "cp", "cp"]
    assert "输出复制失败" in result.stderr
    assert list(temp.rglob("proxies_test.txt"))
    assert not list((project / "node").iterdir())
