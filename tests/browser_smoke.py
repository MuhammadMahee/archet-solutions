"""Optional real-browser flow against Flask with a fake Supabase service.

Run: python tests/browser_smoke.py (requires Playwright and Chromium).
"""
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from werkzeug.serving import make_server
from test_portal import FakeStore, QUOTE
from api import index, portal, sales
from browser_sales import fixture_report


def main():
    fake = FakeStore()
    fake.db("quote_requests", "POST", {**QUOTE, "received_at": "2026-09-25T12:00:00+00:00",
        "phone": "555-0100", "stores": "3", "message": '<script>alert("unsafe")</script>'})
    artifacts = ROOT / "test-results"
    artifacts.mkdir(exist_ok=True)
    server = make_server("127.0.0.1", 0, index.app, threaded=True)
    origin = f"http://127.0.0.1:{server.server_port}"
    with patch.object(portal, "db", fake.db), patch.object(portal, "auth", fake.auth), patch.object(index, "db", fake.db), patch.object(sales, "report_data", fixture_report):
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                owner_context = browser.new_context(viewport={"width": 1440, "height": 1000})
                page = owner_context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(origin + "/internal")
                expect(page.locator("#login")).to_be_visible()
                page.screenshot(path=str(artifacts / "login-desktop.png"), full_page=True)
                page.locator("#login-username").fill("Mahee")
                page.locator("#login-password").fill("TestPass123")
                page.locator("#remember").check()
                page.get_by_role("button", name="Sign in to workspace").click()
                expect(page.locator("#greeting")).to_have_text("Welcome back, Mahee.")
                page.locator('[data-page="overview"]').click()
                expect(page.locator("#stat-total")).to_have_text("1")
                page.screenshot(path=str(artifacts / "workspace-desktop.png"), full_page=True)
                page.get_by_role("button", name="Open →").click()
                expect(page.locator("#quote-message")).to_have_text('<script>alert("unsafe")</script>')
                page.locator("#quote-status").select_option("contacted")
                page.locator("#quote-notes").fill("Browser tested follow-up")
                page.get_by_role("button", name="Save follow-up").click()
                expect(page.locator("#stat-contacted")).to_have_text("1")
                page.get_by_role("button", name="Accounts", exact=False).click()
                page.get_by_role("button", name="Create account").click()
                page.locator("#user-display-name").fill("Team Person")
                page.locator("#user-username").fill("Team_User")
                page.locator("#user-password").fill("TeamPass123")
                page.get_by_role("button", name="Save account").click()
                expect(page.locator("#user-list")).to_contain_text("Team_User")
                page.screenshot(path=str(artifacts / "accounts-desktop.png"), full_page=True)
                member_context = browser.new_context(viewport={"width": 390, "height": 844})
                member = member_context.new_page()
                member.on("pageerror", lambda error: errors.append(str(error)))
                member.goto(origin + "/internal")
                expect(member.locator("#login")).to_be_visible()
                member.screenshot(path=str(artifacts / "login-mobile.png"), full_page=True)
                member.locator("#login-username").fill("team_user")
                member.locator("#login-password").fill("TeamPass123")
                member.get_by_role("button", name="Sign in to workspace").click()
                expect(member.locator("#greeting")).to_have_text("Welcome back, Team.")
                member.locator('[data-page="overview"]').click()
                expect(member.locator("#users-nav")).to_be_hidden()
                assert member.request.get(origin + "/api/internal/users").status == 403
                expect(member.locator("#stat-total")).to_have_text("1")
                assert member.evaluate("document.documentElement.scrollWidth <= innerWidth")
                member.screenshot(path=str(artifacts / "workspace-mobile.png"), full_page=True)
                page.get_by_role("row").filter(has_text="Team_User").get_by_role("button", name="Manage").click()
                page.locator("#user-active").select_option("false")
                page.get_by_role("button", name="Save account").click()
                expect(page.locator("#user-dialog")).not_to_be_visible()
                member.reload()
                expect(member.locator("#login")).to_be_visible()
                page.get_by_role("button", name="Settings").click()
                page.locator("#current-password").fill("TestPass123")
                page.locator("#new-password").fill("ChangedPass123")
                page.locator("#confirm-password").fill("ChangedPass123")
                page.get_by_role("button", name="Update password").click()
                expect(page.locator("#login")).to_be_visible()
                page.locator("#login-password").fill("ChangedPass123")
                page.get_by_role("button", name="Sign in to workspace").click()
                expect(page.locator("#workspace")).to_be_visible()
                page.get_by_role("button", name="Sign out").click()
                expect(page.locator("#login")).to_be_visible()
                assert not errors, errors
                browser.close()
                print("Browser flows passed: login, quotes, account creation, member permissions, mobile layout, disable/revoke, password change, logout. No JS errors.")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
