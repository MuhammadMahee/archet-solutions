"""Whole-sheet copy headers, shared appearance and responsive logo alignment."""
import csv
from io import StringIO
from pathlib import Path
from playwright.sync_api import expect
from browser_store_hours import main

ROOT = Path(__file__).resolve().parents[1]


def check(page):
    def copy_all():
        page.locator('#sh-table td[data-address="A1"]').click()
        page.keyboard.press('Control+a')
        page.keyboard.press('Control+c')
        raw = page.evaluate('navigator.clipboard.readText()')
        rows = list(csv.reader(StringIO(raw), delimiter='\t'))
        labels = page.locator('#sh-table thead .sheet-column-label>span').all_text_contents()
        assert rows[0] == labels, (rows[0],labels)
        assert len(rows) == page.locator('#sh-table tbody tr').count() + 1
        assert all(len(row) == len(labels) for row in rows)
        return raw

    def logo_aligned():
        assert page.locator('.sheet-logo img').evaluate('''img=>{
            const a=img.getBoundingClientRect(),b=img.parentElement.getBoundingClientRect();
            return img.complete && img.naturalWidth>0 && a.left>=b.left && a.right<=b.right+.5 &&
                a.top>=b.top && a.bottom<=b.bottom+.5 && Math.abs((a.top+a.bottom)-(b.top+b.bottom))<1;
        }''')

    logo_aligned()
    page.locator('#sheet-add-column').click()
    page.get_by_label('Column name',exact=True).fill('Notes "review"')
    page.get_by_role('button',name='Save column',exact=True).click()
    expect(page.locator('thead')).to_contain_text('Notes "review"')
    original = page.locator('#sh-table tbody').text_content()
    copy_all()
    # Pasting our full-page copy back must not replace row one with headings.
    page.keyboard.press('Control+v')
    expect(page.locator('#sh-table tbody')).to_have_text(original)
    expect(page.locator('#sheet-message')).not_to_contain_text('Nothing pasted')
    page.locator('#sh-table td[data-address="D1"]').click()
    page.keyboard.press('Control+c')
    assert '\t' not in page.evaluate('navigator.clipboard.readText()')
    page.locator('.sheet-format-bar [data-theme-toggle]').click()
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    expect(page.locator('#sh-table td[data-address="A1"]')).to_have_css('background-color','rgb(17, 31, 48)')
    expect(page.locator('.sheet-presence')).to_have_css('background-color','rgb(20, 34, 53)')
    page.screenshot(path=str(ROOT/'test-results/sheet-dark.png'),full_page=True)
    page.reload()
    expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    copy_all()
    origin = page.url.split('/spreadsheet')[0]
    page.goto(origin+'/compliance?start=2026-10-20&end=2026-10-20')
    expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    expect(page.locator('html')).to_have_attribute('data-theme','dark')
    copy_all()
    logo_aligned()
    page.set_viewport_size({'width':390,'height':844})
    logo_aligned()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('.sheet-format-bar').evaluate('''bar=>Array.from(bar.children).every(el=>getComputedStyle(el).flexShrink==='0')''')
    page.locator('.sheet-format-bar [data-theme-toggle]').click()
    expect(page.locator('html')).to_have_attribute('data-theme','light')
    page.screenshot(path=str(ROOT/'test-results/sheet-logo-mobile.png'),full_page=True)
    print('Sheet appearance/copy passed: headers, custom labels, ordinary copies, paste-back, both spreadsheets, persistence, mobile logo.')


if __name__ == '__main__': main(check,spreadsheet=True)
