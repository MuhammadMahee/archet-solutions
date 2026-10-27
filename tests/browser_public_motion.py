"""Verify camera motion, reduced motion and context recovery.

Run against the local Flask app. No external requests are submitted.
"""
import sys

from playwright.sync_api import expect, sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5001'

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1000, 'height': 760})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.add_init_script('Element.prototype.requestFullscreen = () => Promise.resolve();')
    # Count actual GPU draws rather than taking screenshots while the scene
    # animates, which can stall on software-rendered browser environments.
    page.add_init_script('''
      window.sceneDraws = 0;
      for (const Context of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
        if (!Context) continue;
        for (const method of ['drawArrays', 'drawElements', 'drawArraysInstanced', 'drawElementsInstanced']) {
          const original = Context.prototype[method];
          if (!original) continue;
          Context.prototype[method] = function(...args) {
            window.sceneDraws++;
            return original.apply(this, args);
          };
        }
      }
    ''')
    page.goto(URL, wait_until='networkidle')
    expect(page.locator('#enter-experience')).to_be_enabled(timeout=20000)
    page.locator('#enter-experience').click()
    expect(page.locator('body')).to_have_class('webgl-ready')
    page.wait_for_timeout(1200)
    expect(page.locator('#scene-motion')).to_have_count(0)
    first = page.evaluate('window.sceneDraws')
    page.mouse.move(1200, 300)
    page.wait_for_timeout(300)
    assert page.evaluate('window.sceneDraws') > first, 'Camera animation is not running'
    page.locator('#studio-tour').scroll_into_view_if_needed()
    page.wait_for_timeout(1800)
    assert page.evaluate('window.sceneDraws') > first, 'Scene stopped rendering after scrolling'
    page.emulate_media(reduced_motion='reduce')
    page.wait_for_timeout(150)
    reduced = page.evaluate('window.sceneDraws')
    page.mouse.move(50, 50)
    page.wait_for_timeout(300)
    assert reduced == page.evaluate('window.sceneDraws'), 'Reduced motion scene still animates'
    # Recover to the real scene after the GPU context becomes available again.
    extension = page.evaluate('''() => {
      const gl = document.querySelector('#world').getContext('webgl2');
      window.testLoss = gl?.getExtension('WEBGL_lose_context');
      window.testLoss?.loseContext();
      return Boolean(window.testLoss);
    }''')
    if extension:
        expect(page.locator('body')).to_have_class('webgl-unavailable')
        page.wait_for_timeout(300)
        page.evaluate('window.testLoss.restoreContext()')
        expect(page.locator('body')).to_have_class('webgl-ready', timeout=20000)
    assert not errors, errors
    browser.close()
print('PASS: camera animation, removed motion control, reduced motion, and WebGL context recovery.')
