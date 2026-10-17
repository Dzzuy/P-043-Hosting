"""Real Chrome smoke against Vite/backend/DB; no mocked frontend requests.

Uses an isolated headless browser and the configured demo login through the normal API.
Does not access the user's browser profile or send anything to external chat channels.
"""

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.config import get_settings

ROOT = Path(__file__).resolve().parents[2] / ".tmp"
ROOT.mkdir(exist_ok=True)
INSPECT_ONLY = "--inspect" in sys.argv
ARTIFACTS = ROOT / os.environ.get("WORKSPACE_QA_ARTIFACTS", "workspace_ux_2026-10-16")
ARTIFACTS.mkdir(exist_ok=True)
BASE = "http://localhost:3000"
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
            with httpx.Client(base_url=BASE, timeout=45, trust_env=False) as auth:
                login = auth.post(
                    "/api/v1/auth/login",
                    json={"username": "advisor.demo", "password": dotenv_values(".env")["DEMO_ADVISOR_PASSWORD"]},
                )
                login.raise_for_status()
                cookie_name = get_settings().auth_cookie_name
                call(
                    "POST",
                    "/cookie",
                    {
                        "cookie": {
                            "name": cookie_name,
                            "value": auth.cookies.get(cookie_name),
                            "path": "/",
                            "httpOnly": True,
                            "sameSite": "Lax",
                        }
                    },
                )
            call("POST", "/refresh", {})
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
            original_name = js("return document.querySelector('.sw-customer-name').textContent")
            log(
                "loaded",
                customer=original_name,
                tabs=js("return document.querySelectorAll('.sw-detail-tabs').length"),
                counts=js("return document.querySelector('.sw-conversation-channel').textContent"),
            )
            for width, height in [(1440, 900), (1672, 941), (1024, 900), (390, 844)]:
                call(
                    "POST",
                    "/goog/cdp/execute",
                    {
                        "cmd": "Emulation.setDeviceMetricsOverride",
                        "params": {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False},
                    },
                )
                if width < 768:
                    click(".sw-customer-row.is-selected")
                time.sleep(0.4)
                snapshot(f"{width}_chat")
                metrics = js(
                    "const c=document.querySelector('.sw-conversation').getBoundingClientRect(),dock=document.querySelector('.sw-copilot-dock'),d=dock.getBoundingClientRect(),s=document.querySelector('.sw-chat-surface').getBoundingClientRect(),t=document.querySelector('.sw-composer').getBoundingClientRect(); return {width:innerWidth,height:innerHeight,chatHeight:c.height,drawerClosed:!document.querySelector('.sw-context-drawer'),floating:getComputedStyle(dock).position==='absolute',insideMessages:d.top>=s.top&&d.bottom<=s.bottom,noOverlap:d.bottom<=t.top,horizontalOverflow:document.documentElement.scrollWidth>innerWidth}"
                )
                assert metrics["floating"] and metrics["insideMessages"] and metrics["noOverlap"] and not metrics["horizontalOverflow"], metrics
                log("viewport_chat", **metrics)
                click("//button[contains(@class,'sw-toolbar-button') and contains(.,'Tóm tắt')]", "xpath")
                wait("return !!document.querySelector('.sw-context-drawer .sw-summary-content')")
                assert not js("return !!document.querySelector('.sw-conversation .sw-summary-content')")
                snapshot(f"{width}_summary")
                click(".sw-context-drawer .sw-dialog-heading button")
                wait("return !document.querySelector('.sw-context-drawer')")
                click(".sw-customer-name")
                wait("return !!document.querySelector('.sw-context-drawer')")
                snapshot(f"{width}_profile")
                layout = js(
                    "const d=document.querySelector('.sw-context-drawer').getBoundingClientRect(),c=document.querySelector('.sw-conversation').getBoundingClientRect();return {modal:document.querySelector('.sw-context-drawer').getAttribute('aria-modal'),drawerWidth:d.width,chatWidth:c.width,pushesChat:c.right<=d.left+1}"
                )
                assert layout["drawerWidth"] >= 350 and (
                    layout["pushesChat"] if width >= 1200 else layout["modal"] == "true"
                ), layout
                log("viewport_drawer", width=width, **layout)
                call("POST", f"/element/{element('.sw-context-drawer button')}/value", {"text": "\ue00c"})
                wait("return !document.querySelector('.sw-context-drawer')")
                assert js("return document.activeElement.matches('.sw-customer-name')")
            call(
                "POST",
                "/goog/cdp/execute",
                {
                    "cmd": "Emulation.setDeviceMetricsOverride",
                    "params": {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False},
                },
            )
            loaded_before = js("return document.querySelectorAll('.sw-chat-message').length")
            if js("return !!document.querySelector('.sw-load-older')"):
                click(".sw-load-older")
                wait(f"return document.querySelectorAll('.sw-chat-message').length > {loaded_before}")
                log(
                    "pagination",
                    before=loaded_before,
                    after=js("return document.querySelectorAll('.sw-chat-message').length"),
                )
            click("//button[contains(@class,'sw-toolbar-button') and contains(.,'Tóm tắt')]", "xpath")
            wait("return !!document.querySelector('.sw-context-drawer .sw-summary-content')")
            snapshot("summary")
            click("//button[contains(.,'Xem mốc chăm sóc')]", "xpath")
            wait("return !!document.querySelector('.sw-activities')")
            source_buttons = js("return document.querySelectorAll('.sw-activity .sw-text-button').length")
            if source_buttons:
                click(".sw-activity .sw-text-button")
                wait("return !!document.querySelector('.sw-chat-message.is-highlighted')")
                snapshot("source_highlight")
                log("source_jump", highlighted=True)
            else:
                click(".sw-context-drawer .sw-dialog-heading button")
                log("source_jump", available=False)
            click("//button[contains(@class,'sw-toolbar-button') and contains(.,'Công việc')]", "xpath")
            wait("return !!document.querySelector('.sw-tasks-content')")
            snapshot("tasks")
            log("tasks", groups=js("return [...document.querySelectorAll('.sw-task-group>h3')].map(x=>x.textContent)"))
            click(".sw-tasks-content .sw-inline-heading button")
            wait("return !!document.querySelector('.sw-task-editor')")
            assert js("return document.querySelectorAll('.sw-context-drawer').length===1")
            click("//form[contains(@class,'sw-task-editor')]//button[text()='Hủy']", "xpath")
            click(".sw-context-drawer .sw-dialog-heading button")
            original_draft = js("return document.querySelector('.sw-composer textarea').value")
            original_star = js(
                "return document.querySelector('.sw-customer-title button[aria-pressed]').getAttribute('aria-pressed')"
            )
            draft_text = "[UX QA] Dạ anh, em đang kiểm tra thông tin."
            call("POST", f"/element/{element('.sw-composer textarea')}/clear", {})
            type_text(".sw-composer textarea", draft_text)
            click(".sw-customer-title button[aria-pressed]")
            click(".sw-customer-row:not(.is-selected)")
            wait("return !!document.querySelector('.sw-composer textarea:not(:disabled)')")
            assert js("return document.querySelector('.sw-composer textarea').value") != draft_text
            click("//button[contains(@class,'sw-customer-row') and contains(.,'" + original_name + "')]", "xpath")
            wait(
                "return document.querySelector('.sw-composer textarea')?.value === '[UX QA] Dạ anh, em đang kiểm tra thông tin.'"
            )
            call("POST", "/refresh", {})
            wait("return !!document.querySelector('.desktop-nav-pill')")
            click("//nav[contains(@class,'desktop-nav-pill')]//button[.//span[text()='Trợ lý Copilot']]", "xpath")
            wait("return !!document.querySelector('.sw-composer textarea:not(:disabled)')")
            assert js("return document.querySelector('.sw-composer textarea').value") == draft_text
            assert (
                js(
                    "return document.querySelector('.sw-customer-title button[aria-pressed]').getAttribute('aria-pressed')"
                )
                != original_star
            )
            log("draft_favorite_persistence", reload=True, isolated=True)
            click(".sw-customer-title button[aria-pressed]")
            click(".sw-copilot-bubble")
            wait("return !!document.querySelector('#sw-knowledge-query')")
            wait(
                "return !document.querySelector('.sw-tool-status')?.textContent.includes('Đang tải lịch sử')",
                seconds=45,
            )
            snapshot("copilot")
            if "--skip-lookup" not in sys.argv:
                time.sleep(2)
                previous = js("return document.querySelectorAll('.sw-lookup-assistant').length")
                type_text("#sw-knowledge-query", "So sánh giá VF 3 Plus và VF 5 Plus, chênh lệch bao nhiêu?")
                started = time.monotonic()
                click(".sw-knowledge-form button[type=submit]")
                wait(
                    f"return document.querySelectorAll('.sw-lookup-assistant').length > {previous} || !!document.querySelector('.sw-lookup-error')",
                    seconds=215,
                )
                assert not js("return !!document.querySelector('.sw-lookup-error')"), js(
                    "return document.querySelector('.sw-lookup-error')?.innerText"
                )
                request_id = js("return [...document.querySelectorAll('.sw-lookup-request-id')].at(-1)?.textContent")
                log(
                    "copilot_b",
                    ms=round((time.monotonic() - started) * 1000),
                    request_id=request_id,
                    answer=js("return [...document.querySelectorAll('.sw-lookup-assistant')].at(-1)?.innerText"),
                )
                snapshot("copilot_answer")
                click(".sw-context-drawer .sw-dialog-heading button")
                assert js("return document.querySelector('.sw-composer textarea').value") == draft_text
                call("POST", "/refresh", {})
                wait("return !!document.querySelector('.desktop-nav-pill')")
                click("//nav[contains(@class,'desktop-nav-pill')]//button[.//span[text()='Trợ lý Copilot']]", "xpath")
                wait("return !!document.querySelector('.sw-copilot-bubble')")
                click(".sw-copilot-bubble")
                wait("return !!document.querySelector('.sw-lookup-assistant')")
                wait(
                    "return document.querySelector('.sw-knowledge-log')?.textContent.includes("
                    + json.dumps(request_id)
                    + ")"
                )
                log("copilot_history_reload", restored=True, request_id=request_id)
                snapshot("copilot_reload")
            click(".sw-context-drawer .sw-dialog-heading button")
            call("POST", f"/element/{element('.sw-composer textarea')}/clear", {})
            if original_draft:
                type_text(".sw-composer textarea", original_draft)
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
