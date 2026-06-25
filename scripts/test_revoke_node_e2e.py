"""E2E: revoke a node via the Vigile admin UI.

Bypasses the Playwright login UI by injecting auth tokens into localStorage
*before* the SPA loads via context.add_init_script. Zustand's useAuthStore
reads localStorage in its initial-state factory, so the SPA hydrates
authenticated. Uses 127.0.0.1 explicitly to avoid IPv6 resolution flakiness.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

from playwright.sync_api import Page, sync_playwright

FRONTEND_URL = "http://127.0.0.1:5173"
BACKEND_URL = "http://127.0.0.1:8000"
ADMIN_USER = "admin"
ADMIN_PASS = "admin"


def http_json(
    path: str, method: str = "GET", token: str | None = None, body: dict | None = None
) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BACKEND_URL + path,
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw


def click_plus_button(page: Page) -> bool:
    """Click the + button in the sidebar. Returns True if clicked."""
    candidates = [
        'button[title="Ajouter un serveur"]',
        'button[aria-label="Ajouter un serveur"]',
        "button:has(svg.lucide-plus)",
        'button:has(svg[data-lucide="plus"])',
    ]
    for sel in candidates:
        loc = page.locator(sel).first
        if loc.count() > 0:
            try:
                loc.click(timeout=2000)
                return True
            except Exception:
                continue
    return False


def open_add_node_modal(page: Page) -> bool:
    """Try multiple strategies to open the AddNodeModal."""
    if click_plus_button(page):
        try:
            page.wait_for_selector("text=Ajouter un serveur", timeout=3000)
            return True
        except Exception:
            pass
    try:
        page.locator(
            'button:has-text("Tous les serveurs"), button:has-text("Serveur")'
        ).first.click(timeout=2000)
        time.sleep(0.5)
        if page.locator('button:has-text("AJOUTER SERVEUR")').count() > 0:
            page.locator('button:has-text("AJOUTER SERVEUR")').first.click()
            time.sleep(0.5)
            return True
    except Exception:
        pass
    return False


def main() -> int:
    status, login_data = http_json(
        "/api/auth/login", "POST", body={"username": ADMIN_USER, "password": ADMIN_PASS}
    )
    if status != 200 or not isinstance(login_data, dict):
        print(f"✗ Login failed: {status} {login_data}")
        return 1
    access_token = login_data["access_token"]
    refresh_token = login_data.get("refresh_token") or ""
    user = login_data.get("user") or {"username": ADMIN_USER, "role": "admin", "user_id": "1"}

    print(f"✓ Login OK (role={user.get('role')})")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1400, "height": 900}, ignore_https_errors=True)

        ctx.add_init_script(
            f"""
            try {{
                localStorage.setItem('vigile_access_token', {json.dumps(access_token)});
                localStorage.setItem('vigile_refresh_token', {json.dumps(refresh_token)});
                localStorage.setItem('vigile_user', {json.dumps(json.dumps(user))});
            }} catch (e) {{}}
            """
        )

        page = ctx.new_page()
        console_msgs: list[str] = []
        page.on("pageerror", lambda exc: console_msgs.append(f"[pageerror] {exc}"))
        page.on(
            "console",
            lambda m: (
                console_msgs.append(f"[{m.type}] {m.text}")
                if m.type in ("error", "warning")
                else None
            ),
        )

        page.goto(FRONTEND_URL + "/servers", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_load_state("networkidle", timeout=10000)
        time.sleep(1.5)
        page.screenshot(path="/tmp/vigile_1_servers.png", full_page=True)

        if "/login" in page.url:
            print(f"✗ Redirected to login — auth injection failed")
            print("  URL:", page.url)
            for m in console_msgs[-10:]:
                print("  ", m)
            return 1

        print(f"✓ On {page.url}")

        cards_initial = page.locator("div[role='button']").count()
        print(f"  Initial cards: {cards_initial}")

        test_name = f"e2e-revoke-{int(time.time())}"
        node_id: str | None = None
        if not open_add_node_modal(page):
            print("⚠ Could not open AddNodeModal via UI; falling back to API")
            status, resp = http_json(
                "/api/nodes/generate-join", "POST", token=access_token, body={"name": test_name}
            )
            if status != 201:
                print(f"✗ API create failed: {status} {resp}")
                return 1
            node_id = resp["node_id"]
            print(f"  Created via API: {node_id}")
            page.reload(wait_until="networkidle", timeout=15000)
            time.sleep(2)
        else:
            print(f"✓ AddNodeModal open")
            name_input = page.locator('input[required][type="text"]').first
            if name_input.count() == 0:
                name_input = page.locator('input[type="text"]').first
            name_input.fill(test_name)
            page.screenshot(path="/tmp/vigile_2_addmodal_filled.png", full_page=True)
            submit_btn = page.locator('button[type="submit"]').first
            submit_btn.click()
            try:
                page.wait_for_selector("text=Jeton généré", timeout=10000)
            except Exception:
                page.screenshot(path="/tmp/vigile_2b_addmodal_after_submit.png", full_page=True)
                print("⚠ Modal did not transition to 'Jeton généré'")
            time.sleep(1)
            page.screenshot(path="/tmp/vigile_3_generated.png", full_page=True)
            try:
                page.locator("button:has(svg.lucide-x)").first.click(timeout=2000)
            except Exception:
                page.keyboard.press("Escape")
            time.sleep(1)
            page.reload(wait_until="networkidle", timeout=15000)
            time.sleep(2)

        try:
            page.wait_for_selector(f"text={test_name}", timeout=10000)
        except Exception:
            page.screenshot(path="/tmp/vigile_4_no_card.png", full_page=True)
            print(f"✗ New card '{test_name}' did not appear")
            for m in console_msgs[-10:]:
                print("  ", m)
            return 1

        new_card = page.locator(f"div[role='button']:has-text('{test_name}')").first
        cards_after_add = page.locator("div[role='button']").count()
        print(f"✓ New card visible: '{test_name}' (total cards: {cards_after_add})")
        page.screenshot(path="/tmp/vigile_5_card_visible.png", full_page=True)

        if node_id is None:
            status, nodes_resp = http_json("/api/nodes", token=access_token)
            if isinstance(nodes_resp, list):
                match = next((n for n in nodes_resp if n.get("name") == test_name), None)
                if match:
                    node_id = match["id"]
            if node_id is None:
                print("✗ Could not resolve node_id from API")
                return 1

        kebab = new_card.locator('button[aria-label="Plus d\'actions"]').first
        if kebab.count() == 0:
            kebab = new_card.locator(
                'button:has(svg.lucide-ellipsis-vertical), button:has(svg[data-lucide="more-vertical"])'
            ).first
        kebab.scroll_into_view_if_needed()
        kebab.click()
        time.sleep(0.5)
        page.screenshot(path="/tmp/vigile_6_kebab.png", full_page=True)

        delete_btn = page.locator('button:has-text("Supprimer")').last
        if delete_btn.count() == 0:
            print("✗ 'Supprimer' not found in kebab menu")
            for m in console_msgs[-10:]:
                print("  ", m)
            return 1
        delete_btn.click()
        time.sleep(0.5)
        page.screenshot(path="/tmp/vigile_7_confirm_modal.png", full_page=True)

        confirm_input = page.locator('input[placeholder*="confirmer"]').first
        if confirm_input.count() == 0:
            print("✗ Confirm input not found")
            return 1
        confirm_input.fill(test_name)
        time.sleep(0.3)

        revoke_btn = page.locator('button[type="submit"]:has-text("Révoquer")').first
        if revoke_btn.count() == 0:
            print("✗ 'Révoquer' button not found")
            return 1
        revoke_btn.click()

        try:
            page.wait_for_selector(f"text={test_name}", state="detached", timeout=10000)
            card_disappeared = True
        except Exception:
            card_disappeared = False

        time.sleep(2)
        page.screenshot(path="/tmp/vigile_8_after_revoke.png", full_page=True)

        node_not_found = False
        for _ in range(15):
            try:
                if page.locator("text=Node not found").first.is_visible(timeout=200):
                    node_not_found = True
                    break
            except Exception:
                pass
            time.sleep(0.3)

        cards_after_revoke = page.locator("div[role='button']").count()
        status, nodes_resp = http_json("/api/nodes", token=access_token)
        remaining_with_test_name = []
        if isinstance(nodes_resp, list):
            remaining_with_test_name = [n for n in nodes_resp if n.get("name") == test_name]

        status, deleted_node = http_json(f"/api/nodes/{node_id}", token=access_token)
        api_node_gone = status == 404

        print()
        print("=" * 50)
        print("RESULTS")
        print("=" * 50)
        print(f"  Initial cards         : {cards_initial}")
        print(f"  After add             : {cards_after_add}")
        print(f"  After revoke          : {cards_after_revoke}")
        print(f"  Card disappeared      : {card_disappeared}")
        print(f"  'Node not found' toast: {node_not_found}")
        print(f"  API: nodes w/ test name remaining: {len(remaining_with_test_name)}")
        print(f"  API: GET /nodes/{{id}} status       : {status} (expect 404)")
        if console_msgs:
            print()
            print("Console messages (last 10):")
            for m in console_msgs[-10:]:
                print(f"  {m}")

        ok = (
            not node_not_found
            and card_disappeared
            and cards_after_revoke == cards_initial
            and len(remaining_with_test_name) == 0
            and api_node_gone
        )
        if ok:
            print("\n✓ PASS: revoke via UI works end-to-end")
            browser.close()
            return 0
        print("\n✗ FAIL: see criteria above")
        browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
