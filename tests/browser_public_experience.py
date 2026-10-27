"""Public marketing experience checks; quote requests are always intercepted.

Run: python tests/browser_public_experience.py [http://127.0.0.1:5001]
"""
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5001'
OUTPUT = Path('test-results/public-experience')
OUTPUT.mkdir(parents=True, exist_ok=True)


def enter(page):
    page.goto(BASE_URL, wait_until='networkidle')
    expect(page.locator('#enter-experience')).to_be_enabled(timeout=20000)
    expect(page.locator('#enter-label')).to_have_text('Click anywhere to continue')
    page.locator('#enter-experience').click()
    expect(page.locator('body')).not_to_have_class('is-loading')
    page.wait_for_timeout(900)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1440, 'height': 1000})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    # Browser environments may reject fullscreen; both cases must enter the site.
    page.add_init_script('Element.prototype.requestFullscreen = () => Promise.reject(new Error("Test fullscreen denial"));')
    enter(page)
    expect(page.locator('body')).to_have_class('webgl-ready')
    assert page.locator('main').evaluate('(node) => !node.inert')
    page.screenshot(path=str(OUTPUT / 'desktop.png'))
    page.emulate_media(reduced_motion='reduce')
    page.locator('[data-industry="retail"]').click()
    expect(page.locator('#servicesGrid article')).to_have_count(8)
    expect(page.locator('#servicesGrid')).to_contain_text('Revenue Reconciliation')
    expect(page.locator('[name="brand"]')).to_have_value('Gas Station / Vape Shop')
    page.locator('[data-industry="telecom"]').click()
    page.locator('[data-brand="AT&T"]').click()
    expect(page.locator('#activeBrandName')).to_have_text('AT&T')
    expect(page.locator('[name="brand"]')).to_have_value('AT&T')
    page.locator('[data-service="Live Surveillance"]').click()
    expect(page.locator('[name="message"]')).to_have_value("I'm interested in Live Surveillance.")
    page.locator('[data-digital]').first.click()
    expect(page.locator('[name="brand"]')).to_have_value('Website Development & Design')
    assert 'Live Surveillance' in page.locator('[name="message"]').input_value()
    page.locator('[name="full_name"]').fill('Browser Test')
    page.locator('[name="company"]').fill('QA Company')
    page.locator('[name="email"]').fill('test@example.com')
    payloads = []
    def fail_quote(route):
        payloads.append(route.request.post_data_json)
        route.fulfill(status=503, content_type='application/json', body=json.dumps({'status': 'error', 'message': 'Please try again shortly.'}))
    page.route('**/api/quote', fail_quote)
    page.locator('#quoteForm [type="submit"]').click()
    expect(page.locator('#formMsg')).to_have_text('Please try again shortly.')
    expect(page.locator('[name="full_name"]')).to_have_value('Browser Test')
    assert payloads[0]['brand'] == 'Website Development & Design'
    assert 'Website Development' in payloads[0]['message']
    page.unroute('**/api/quote', fail_quote)
    page.route('**/api/quote', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'status': 'success', 'message': 'Thank you. Your request is received.'})))
    page.locator('#quoteForm [type="submit"]').click()
    expect(page.locator('#formMsg')).to_have_class('success')
    expect(page.locator('[name="full_name"]')).to_have_value('')
    page.screenshot(path=str(OUTPUT / 'contact.png'))
    assert not errors, errors
    for width, height in [(390, 844), (320, 740), (768, 1024)]:
        mobile = browser.new_page(viewport={'width': width, 'height': height}, reduced_motion='reduce')
        mobile.on('pageerror', lambda error: errors.append(str(error)))
        enter(mobile)
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Overflow at {width}'
        mobile.screenshot(path=str(OUTPUT / f'width-{width}.png'))
        if width < 700:
            mobile.locator('.menu-toggle').click()
            expect(mobile.locator('.menu-toggle')).to_have_attribute('aria-expanded', 'true')
            mobile.keyboard.press('Escape')
            expect(mobile.locator('.menu-toggle')).to_have_attribute('aria-expanded', 'false')
        mobile.locator('#contact').scroll_into_view_if_needed()
        assert mobile.evaluate('document.documentElement.scrollWidth <= innerWidth'), f'Contact overflow at {width}'
        mobile.screenshot(path=str(OUTPUT / f'contact-{width}.png'))
        mobile.close()
    fallback = browser.new_page(viewport={'width': 1200, 'height': 900})
    fallback.add_init_script('const original = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function(type, ...args) { return type.includes("webgl") ? null : original.call(this, type, ...args); };')
    enter(fallback)
    expect(fallback.locator('body')).to_have_class('webgl-unavailable')
    fallback.screenshot(path=str(OUTPUT / 'fallback.png'))
    fallback.close()
    missing = browser.new_page()
    missing.route('**/public-scene.js', lambda route: route.abort())
    enter(missing)
    expect(missing.locator('#quoteForm')).to_be_attached()
    missing.close()
    assert not errors, errors
    assert page.request.get(BASE_URL + '/assets/public-three-LICENSE.txt').status == 200
    assert page.request.get(BASE_URL + '/assets/not-public.txt').status == 404
    browser.close()
print('PASS: 3D readiness, fallback, responsive layouts, menu, industries, service enquiries, and mocked quote success/failure.')
