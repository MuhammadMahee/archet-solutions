"""Verify camera motion, pause, reduced motion and context recovery.

Run against the local Flask app. No external requests are submitted.
"""
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5001'
OUTPUT = Path('test-results/public-experience')
OUTPUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script('Element.prototype.requestFullscreen = () => Promise.resolve();')
    page.goto(URL, wait_until='networkidle')
    expect(page.locator('#enter-experience')).to_be_enabled(timeout=20000)
    page.locator('#enter-experience').click()
    expect(page.locator('body')).to_have_class('webgl-ready')
    page.wait_for_timeout(1200)
    control = page.locator('#scene-motion')
    control.click()
    expect(control).to_have_text('Play motion')
    expect(control).to_have_attribute('aria-pressed', 'true')
    page.wait_for_timeout(150)
    first = page.locator('#world').screenshot()
    page.mouse.move(1200, 300)
    page.wait_for_timeout(300)
    assert first == page.locator('#world').screenshot(), 'Paused camera still moves'
    page.screenshot(path=str(OUTPUT / 'cinematic-desktop-final.png'))
    control.click()
    expect(control).to_have_text('Pause motion')
    page.locator('#studio-tour').scroll_into_view_if_needed()
    page.wait_for_timeout(1800)
    control.click()
    page.wait_for_timeout(150)
    assert first != page.locator('#world').screenshot(), 'Scroll did not move the camera'
    page.screenshot(path=str(OUTPUT / 'cinematic-studio-final.png'))
    page.emulate_media(reduced_motion='reduce')
    expect(control).to_have_text('Motion reduced')
    expect(control).to_be_disabled()
    reduced = page.locator('#world').screenshot()
    page.mouse.move(50, 50)
    page.wait_for_timeout(300)
    assert reduced == page.locator('#world').screenshot(), 'Reduced motion camera still moves'
    # Recover to the real scene after the GPU context becomes available again.
    extension = page.evaluate('''() => {
      const gl = document.querySelector('#world').getContext('webgl2');
      window.testLoss = gl?.getExtension('WEBGL_lose_context');
      window.testLoss?.loseContext();
      return Boolean(window.testLoss);
    }''')
    if extension:
        expect(page.locator('body')).to_have_class('webgl-unavailable')
        expect(control).to_be_hidden()
        page.wait_for_timeout(300)
        page.evaluate('window.testLoss.restoreContext()')
        expect(page.locator('body')).to_have_class('webgl-ready', timeout=20000)
        expect(control).to_be_visible()
    assert not errors, errors
    browser.close()
print('PASS: camera travel, motion pause, reduced motion, and WebGL context recovery.')
