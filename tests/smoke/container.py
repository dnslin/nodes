"""Run on the Docker host: verify exit status and interruption delivery offline."""

import subprocess
import sys
import time
import uuid


def docker(*arguments, **kwargs):
    return subprocess.run(
        ["docker", *arguments], capture_output=True, text=True, check=True, **kwargs
    ).stdout.strip()


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else "ghcr.io/dnslin/nodes:latest"
    exit_name = f"nodes-exit-smoke-{uuid.uuid4().hex[:10]}"
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                exit_name,
                image,
                "python",
                "-c",
                "raise SystemExit(23)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 23, result
    finally:
        subprocess.run(["docker", "rm", "-f", exit_name], capture_output=True, check=False)
    name = f"nodes-signal-smoke-{uuid.uuid4().hex[:10]}"
    try:
        docker(
            "run",
            "-d",
            "--name",
            name,
            image,
            "python",
            "-u",
            "-c",
            "import signal,sys,time; "
            "signal.signal(signal.SIGINT, lambda *_: "
            '(print("SIGINT received", flush=True), time.sleep(0.2), '
            'print("cleanup complete", flush=True), sys.exit(0))); '
            'print("ready", flush=True); time.sleep(120)',
        )
        deadline = time.monotonic() + 15
        while "ready" not in docker("logs", name):
            if time.monotonic() >= deadline:
                raise AssertionError("Python did not start in the container")
            time.sleep(0.1)
        docker("stop", "--time", "5", name, timeout=15)
        assert docker("wait", name, timeout=15) == "130", "Default stop did not exit with SIGINT"
        logs = docker("logs", name)
        assert "SIGINT received" in logs, "Default Docker stop did not deliver SIGINT to Python"
        assert "cleanup complete" in logs, "Docker stopped before Python finished cleanup"
        print("PASS: exit status preserved; Docker stop delivers SIGINT and completes cleanup.")
    finally:
        docker("rm", "-f", name)


if __name__ == "__main__":
    main()
