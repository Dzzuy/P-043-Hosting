"""Interaction QA against the isolated fixture; no LLM or real customer writes."""

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

ROOT = Path(__file__).resolve().parents[2] / ".tmp"
ROOT.mkdir(exist_ok=True)
INSPECT_ONLY = "--inspect" in sys.argv
ARTIFACTS = ROOT / os.environ.get("WORKSPACE_QA_ARTIFACTS", "workspace_ux_fixture_2026-10-16")
ARTIFACTS.mkdir(exist_ok=True)
BASE = "http://localhost:8002"
DRIVER = os.environ.get("CHROMEDRIVER_PATH") or str(
    sorted(
        (Path.home() / ".cache/selenium/chromedriver/win64").glob("*/chromedriver.exe"),
        key=lambda path: path.stat().st_mtime,
    )[-1]
)
ELEMENT = "element-6066-11e4-a52e-4f735466cecf"
rows = []


def log(case, **data):
    row = {"case": case, **data}
    rows.append(row)
    print(json.dumps(row, ensure_ascii=True), flush=True)
    (ARTIFACTS / "results.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    with (ARTIFACTS / "driver.log").open("w", encoding="utf-8") as driver_log:
        process = subprocess.Popen(
            [DRIVER, f"--port={port}", "--allowed-ips=127.0.0.1"],
            stdout=driver_log,
            stderr=driver_log,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False)
        sid = None
        try:
            for _ in range(40):
                try:
                    if client.get("/status").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.25)
            response = client.post(
                "/session",
                json={
                    "capabilities": {
                        "alwaysMatch": {
                            "browserName": "chrome",
                            "goog:chromeOptions": {
                                "binary": os.environ.get(
                                    "CHROME_BINARY", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
                                ),
                                "args": [
                                    "--headless=new",
                                    "--window-size=1440,1000",
                                    "--no-first-run",
                                    "--no-default-browser-check",
                                ],
                            },
                            "goog:loggingPrefs": {"browser": "ALL", "performance": "ALL"},
                        }
                    }
                },
            )
            value = response.json()["value"]
            if "sessionId" not in value:
                raise RuntimeError(f"Chrome session failed: {value.get('error')}: {value.get('message', '')[:300]}")
            sid = value["sessionId"]

            def call(method, path, data=None):
                r = client.request(method, f"/session/{sid}{path}", json=data)
                result = r.json().get("value")
                if r.status_code >= 400:
                    raise RuntimeError(str(result)[:700])
                return result

            def js(script, *args):
                return call("POST", "/execute/sync", {"script": script, "args": list(args)})

            def wait(script, seconds=45):
                deadline = time.monotonic() + seconds
                while time.monotonic() < deadline:
                    result = js(script)
                    if result:
                        return result
                    time.sleep(0.4)
                raise RuntimeError("Browser wait timed out: " + script)

            def element(selector, using="css selector"):
                return call("POST", "/element", {"using": using, "value": selector})[ELEMENT]

            def click(selector, using="css selector"):
                call("POST", f"/element/{element(selector, using)}/click", {})

            def type_text(selector, value):
                call("POST", f"/element/{element(selector)}/value", {"text": value})

            def snapshot(name):
                (ARTIFACTS / f"{name}.html").write_text(call("GET", "/source"), encoding="utf-8")
                (ARTIFACTS / f"{name}.png").write_bytes(base64.b64decode(call("GET", "/screenshot")))

            def network():
                entries = call("POST", "/se/log", {"type": "performance"})
                requests, events = {}, []
                for entry in entries:
                    event = json.loads(entry["message"])["message"]
                    params = event.get("params", {})
                    if event["method"] == "Network.requestWillBeSent":
                        request = params["request"]
                        if "/api/" in request["url"]:
                            requests[params["requestId"]] = {
                                "url": request["url"],
                                "method": request["method"],
                                "start": params["timestamp"],
                            }
                    elif event["method"] == "Network.responseReceived" and params["requestId"] in requests:
                        request = requests[params["requestId"]]
                        events.append(
                            {
                                "url": request["url"],
                                "method": request["method"],
                                "status": params["response"]["status"],
                                "ms": round((params["timestamp"] - request["start"]) * 1000),
                            }
                        )
                (ARTIFACTS / "network.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
                errors = call("POST", "/se/log", {"type": "browser"})
                (ARTIFACTS / "console.json").write_text(json.dumps(errors, indent=2), encoding="utf-8")
                return events

            call("POST", "/goog/cdp/execute", {"cmd": "Network.setCacheDisabled", "params": {"cacheDisabled": True}})
            call("POST", "/url", {"url": BASE})
            wait("return !!document.querySelector('.desktop-nav-pill')")
            click("//nav[contains(@class,'desktop-nav-pill')]//button[.//span[text()='Trợ lý Copilot']]", "xpath")
            if INSPECT_ONLY:
                state = wait(
                    "return document.querySelector('.sw-customer-row') ? 'customers' : document.querySelector('.sw-customer-rows .sw-empty')?.innerText"
                )
                log("workspace_current_state", state=state)
                snapshot("01_workspace_current_state")
                log("network_summary", events=network())
                return
            wait("return !!document.querySelector('.sw-customer-row')")
            wait("return !!document.querySelector('.sw-composer textarea:not(:disabled)')")
            log("fixture_loaded", counts=js("return document.querySelector('.sw-conversation-channel').textContent"))
            assert js("return document.querySelectorAll('.sw-chat-message').length") == 30
            click("//button[contains(@class,'sw-toolbar-button') and contains(.,'Tóm tắt')]", "xpath")
            wait("return !!document.querySelector('.sw-context-drawer .sw-summary-content')")
            assert not js("return !!document.querySelector('.sw-conversation .sw-summary-content')")
            assert js("return document.querySelector('.sw-summary-content').textContent.includes('5 tin nhắn mới')")
            click("//button[contains(.,'Xem mốc chăm sóc')]", "xpath")
            click(".sw-activity .sw-text-button")
            wait("return !!document.querySelector('.sw-chat-message.is-highlighted')")
            assert js(
                "return document.querySelector('.sw-chat-message.is-highlighted').textContent.includes('Tin nguồn kiểm thử 1')"
            )
            log(
                "old_source_lazy_load",
                highlighted=True,
                loaded=js("return document.querySelectorAll('.sw-chat-message').length"),
            )
            snapshot("old_source_highlight")
            click(".sw-customer-name")
            click("//dl//div[dt[text()='Nhu cầu chính']]//button[contains(.,'Xác nhận / Sửa')]", "xpath")
            call("POST", f"/element/{element('.sw-fact-editor input')}/clear", {})
            type_text(".sw-fact-editor input", "Đi làm và đưa con")
            click(".sw-fact-editor button[type=submit]")
            wait("return !!document.querySelector('.sw-confirmed')")
            assert js("return document.querySelector('.sw-profile-content').textContent.includes('Đi làm và đưa con')")
            log("profile_confirm", saved=True)
            click(".sw-context-drawer .sw-dialog-heading button")
            click("//button[contains(@class,'sw-toolbar-button') and contains(.,'Công việc')]", "xpath")
            click(".sw-task-check input")
            wait("return !!document.querySelector('.sw-task-row.is-completed')")
            assert js("return document.querySelector('.sw-tool-count').textContent") == "0"
            click(".sw-task-check input")
            wait("return !document.querySelector('.sw-task-row.is-completed')")
            assert js("return document.querySelector('.sw-tool-count').textContent") == "1"
            click(".sw-task-actions button")
            call("POST", f"/element/{element('.sw-task-editor input')}/clear", {})
            type_text(".sw-task-editor input", "Gọi lại theo lịch đã sửa")
            click(".sw-task-editor button[type=submit]")
            wait("return !document.querySelector('.sw-task-editor')")
            assert js(
                "return document.querySelector('.sw-task-check').textContent.includes('Gọi lại theo lịch đã sửa')"
            )
            click(".sw-tasks-content .sw-inline-heading button")
            type_text(".sw-task-editor input", "Công việc QA thủ công")
            click(".sw-task-editor button[type=submit]")
            wait("return document.querySelectorAll('.sw-task-row').length===2")
            assert js("return document.querySelectorAll('.sw-context-drawer').length") == 1
            log("task_create_edit_complete_reopen", passed=True)
            click(".sw-composer textarea")
            call("POST", f"/element/{element('.sw-composer textarea')}/value", {"text": "\ue00c"})
            wait("return !document.querySelector('.sw-context-drawer')")
            log("escape_from_chat", closed=True)
            type_text(".sw-composer textarea", "Tin sales đang soạn")
            click(".sw-draft-trigger")
            wait("return !!document.querySelector('.sw-draft-text')")
            call(
                "POST",
                "/goog/cdp/execute",
                {
                    "cmd": "Browser.grantPermissions",
                    "params": {"origin": BASE, "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"]},
                },
            )
            click("//section[contains(@class,'sw-inline-draft')]//button[text()='Sao chép']", "xpath")
            wait("return document.querySelector('.sw-toast').textContent.includes('Đã sao chép')")
            assert js("return document.querySelector('.sw-composer textarea').value") == "Tin sales đang soạn"
            click("//section[contains(@class,'sw-inline-draft')]//button[text()='Chèn thêm']", "xpath")
            assert (
                js("return document.querySelector('.sw-composer textarea').value")
                == "Tin sales đang soạn\n\nBản nháp QA đã kiểm tra."
            )
            click(".sw-draft-trigger")
            click("//section[contains(@class,'sw-inline-draft')]//button[text()='Thay thế']", "xpath")
            assert js("return document.querySelector('.sw-composer textarea').value") == "Bản nháp QA đã kiểm tra."
            log("draft_copy_append_replace", passed=True)
            snapshot("draft_applied")
            click(".sw-send-button")
            wait("return document.querySelector('.sw-composer textarea').value===''")
            click(".sw-draft-trigger")
            assert js(
                "return document.querySelector('.sw-inline-draft .sw-freshness').textContent.includes('chưa bao gồm tin mới')"
            )
            assert js(
                "return [...document.querySelectorAll('.sw-inline-draft button')].some(x=>x.textContent.includes('Dùng bản nháp')&&x.disabled)"
            )
            log("saved_message_stales_draft", passed=True)
            click('[aria-label="Đóng gợi ý trả lời"]')
            click(".sw-stage-trigger")
            select = element(".sw-stage-popover select")
            call("POST", f"/element/{select}/value", {"text": "Đã hẹn xem xe"})
            click(".sw-stage-popover button[type=submit]")
            wait("return !document.querySelector('.sw-stage-popover')")
            stage_before = js("return document.querySelector('.sw-stage-trigger').textContent")
            click("//button[contains(@class,'sw-toolbar-button') and contains(.,'Tóm tắt')]", "xpath")
            click("//section[contains(@class,'sw-summary-content')]//button[contains(.,'Cập nhật phân tích')]", "xpath")
            wait("return !!document.querySelector('.sw-analysis-changes')")
            assert js("return document.querySelector('.sw-stage-trigger').textContent") == stage_before
            assert not js("return !!document.querySelector('.sw-summary-content .sw-freshness')")
            click(".sw-analysis-changes summary")
            snapshot("analysis_changes")
            log("explicit_analysis_freshness_and_manual_stage", passed=True)
            log("network_summary", events=network())
        except Exception as exc:
            log("failure", error=str(exc))
            if sid:
                try:
                    snapshot("failure")
                    network()
                except Exception:
                    pass
            raise
        finally:
            if sid:
                client.delete(f"/session/{sid}")
            client.close()
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
