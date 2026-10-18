"""A failing hook must not be reported as a successful Python invocation."""

import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name != "nt", reason="Windows cmd launcher")
@pytest.mark.parametrize("code", [0, 7])
def test_windows_launcher_propagates_python_exit_status(code):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "scripts\\_pyrun.cmd", "-c", f"import sys; print('python-invoked'); sys.exit({code})"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert "python-invoked" in result.stdout
    assert result.returncode == code
