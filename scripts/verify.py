"""既存make checkの全検証を保持し、完全ログとは別に結果を要約する。"""

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from uuid import uuid4


def run_command(command: list[str], root: Path, stream, timeout: int = 600) -> int:
    """停止時に孫プロセスも回収し、不完全実行を失敗にする。"""
    try:
        process = subprocess.Popen(
            command, cwd=root, stdout=stream, stderr=stream, start_new_session=True
        )
    except OSError as error:
        stream.write(str(error))
        return 127
    try:
        return process.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        stream.write("verification interrupted or timed out\n")
        return 124


def interrupted(signum, frame):
    """SIGTERMも結果記録とプロセス回収へ進める。"""
    raise KeyboardInterrupt


def main() -> int:
    """秘密を使わない既存の検証だけを実行する。"""
    root = Path(__file__).resolve().parents[1]
    signal.signal(signal.SIGTERM, interrupted)
    os.umask(0o077)
    output = (
        root
        / ".verify"
        / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid4().hex[:8])
    )
    output.mkdir(parents=True)
    started = time.perf_counter()
    commands = [
        ["uv", "run", "ruff", "check", "scripts", "tests"],
        ["uv", "run", "ruff", "format", "--check", "scripts", "tests"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        ["terraform", "-chdir=terraform", "fmt", "-check", "-recursive"],
        [sys.executable, "-m", "scripts.deploy", "validate"],
    ]
    results = []
    for index, command in enumerate(commands):
        path = output / f"{index}.log"
        start = time.perf_counter()
        with path.open("w") as stream:
            code = run_command(command, root, stream)
        results.append(
            {
                "command": command,
                "exit_code": code,
                "seconds": round(time.perf_counter() - start, 3),
            }
        )
        if code:
            print(path.read_text(errors="replace")[-4000:])
            break
    success = len(results) == len(commands) and all(
        r["exit_code"] == 0 for r in results
    )
    summary = {
        "status": "passed" if success else "failed",
        "complete": len(results) == len(commands),
        "seconds": round(time.perf_counter() - started, 3),
        "steps": results,
        "run": str(output),
    }
    (output / "result.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
