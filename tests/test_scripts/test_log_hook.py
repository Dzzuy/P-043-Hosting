"""Prompt-only AI logging must not turn lifecycle hooks into fake user prompts."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import log_hook


@pytest.mark.parametrize(
    ("tool", "event"),
    [
        ("codex", "Stop"),
        ("cursor", "stop"),
        ("gemini", "AfterModel"),
        ("gemini", "SessionEnd"),
        ("copilot", "sessionEnd"),
    ],
)
def test_lifecycle_events_are_not_logged(tool: str, event: str) -> None:
    assert log_hook.normalize({"hook_event_name": event}, tool) is None


def test_empty_prompt_is_not_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_hook, "git", lambda _command: "P-043.git")

    assert log_hook.normalize({"hook_event_name": "UserPromptSubmit", "prompt": "   "}, "codex") is None


def test_user_prompt_keeps_auto_log_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_hook, "git", lambda _command: "P-043.git")

    entry = log_hook.normalize(
        {"hook_event_name": "UserPromptSubmit", "prompt": "Giá VF 8?", "session_id": "session-1"},
        "codex",
    )

    assert entry is not None
    assert entry["event"] == "UserPromptSubmit"
    assert entry["prompt"] == "Giá VF 8?"
    assert entry["session_id"] == "session-1"


@pytest.mark.parametrize("prompt", [None, 42, [], {}])
def test_invalid_prompt_is_ignored(prompt):
    assert log_hook.normalize({"hook_event_name": "UserPromptSubmit", "prompt": prompt}, "codex") is None


def test_codex_capture_from_subdirectory(tmp_path):
    root = Path(__file__).resolve().parents[2]
    payload = {"hookEventName": "UserPromptSubmit", "prompt": "Kiểm tra log giả", "sessionId": "synthetic"}
    result = subprocess.run(
        [sys.executable, str(root / "scripts/log_hook.py"), "--tool=codex"],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        cwd=root / "frontend", env={**os.environ, "AI_LOG_DIR": str(tmp_path / "nested/logs")},
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {}
    entry = json.loads((tmp_path / "nested/logs/session.jsonl").read_text(encoding="utf-8"))
    assert entry["prompt"] == payload["prompt"]
    assert entry["session_id"] == "synthetic"
    assert entry["repo"] == "P-043"
    assert entry["commit"]


def test_pre_push_reports_failures_without_blocking(tmp_path):
    import shutil

    bash = shutil.which("bash")
    git_bash = Path("D:/My SoftWare/Git/bin/bash.exe")
    if git_bash.exists():
        bash = str(git_bash)
    if not bash:
        pytest.skip("Bash unavailable")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "_pyrun.sh").write_text('echo "$1" >&2\nexit 7\n', encoding="utf-8")
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run([bash, str(root / "scripts/hooks/pre-push")], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0
    assert "pre-push:" in result.stderr
    assert "scripts/log_antigravity.py" in result.stderr
    assert "scripts/submit_log.py" in result.stderr
    assert "Log submission failed" in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows Codex command")
@pytest.mark.parametrize("through_powershell", [False, True])
def test_configured_windows_hook_preserves_utf8(tmp_path, through_powershell):
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / ".codex/hooks.json").read_text(encoding="utf-8"))
    command = config["hooks"]["UserPromptSubmit"][0]["hooks"][0]["commandWindows"]
    if through_powershell:
        # Codex executes the handler through a shell. Direct CreateProcess alone
        # misses nested PowerShell quoting errors that prevent the hook running.
        command = ["powershell", "-NoProfile", "-Command", command]
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "Ghi thử tiếng Việt", "session_id": "synthetic"}
    result = subprocess.run(
        command, input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        cwd=root / "frontend", env={**os.environ, "AI_LOG_DIR": str(tmp_path)}, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    entry = json.loads((tmp_path / "session.jsonl").read_text(encoding="utf-8"))
    assert entry["prompt"] == payload["prompt"]
