"""Verify submission with a mock transport; never upload real prompts in tests."""

import json
from urllib.error import URLError

import pytest

from scripts import submit_log


@pytest.mark.parametrize("failure", [False, True])
def test_submission_archives_success_and_preserves_failure(tmp_path, monkeypatch, capsys, failure):
    entry = {"tool": "codex", "prompt": "synthetic test"}
    active = tmp_path / "session.jsonl"
    active.write_text(json.dumps(entry) + "\n", encoding="utf-8")
    monkeypatch.setattr(submit_log, "LOG_FILE", active)
    monkeypatch.setattr(submit_log, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(submit_log, "SERVER_URL", "https://example.invalid/log")
    monkeypatch.setattr(submit_log, "API_KEY", "synthetic-key")

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def transport(request, timeout):
        assert json.loads(request.data) == {"entries": [entry]}
        assert request.get_header("Authorization") == "Bearer synthetic-key"
        assert timeout == 10
        if failure:
            raise URLError("simulated outage")
        return Response()

    monkeypatch.setattr(submit_log.urllib.request, "urlopen", transport)
    if failure:
        with pytest.raises(SystemExit) as error:
            submit_log.main()
        assert error.value.code == 0
        assert json.loads(active.read_text()) == entry
        assert "logs kept locally" in capsys.readouterr().err
    else:
        submit_log.main()
        assert not active.exists()
        archived = list((tmp_path / "archive").glob("*.jsonl"))
        assert len(archived) == 1
        assert json.loads(archived[0].read_text()) == entry
        assert "Submitted 1 entries" in capsys.readouterr().err
