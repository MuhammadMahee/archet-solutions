"""Exercise autosave races, retry, clipboard movement, selection, and historical dates."""
from pathlib import Path
from playwright.sync_api import expect
from browser_store_hours import main

ROOT = Path(__file__).resolve().parents[1]


def check(page):
    def cell(address):
        return page.locator(f'#sh-table [data-address="{address}"]')

    def go(address):
        page.locator('#sh-grid-address').fill(address)
        page.locator('#sh-grid-address').press('Enter')

    def edit(address, value):
        go(address)
        page.keyboard.press('F2')
        page.get_by_label('Edit '+address,exact=True).fill(value)
        page.keyboard.press('Enter')

    def saved():
        expect(page.locator('#sheet-save-state')).to_have_text('All changes saved', timeout=15000)

    expect(page.locator('.sheet-logo img')).to_have_attribute('src', '/archet-logo.png')
    assert page.locator('.sheet-logo img').evaluate('(img)=>img.complete && img.naturalWidth>0')
    go('D1')
    expect(cell('D1')).to_have_css('outline-color', 'rgb(24, 92, 55)')
    page.keyboard.press('Shift+Space')
    expect(page.locator('.sh-cell-selected')).to_have_count(14)
    page.keyboard.press('Control+Space')
    expect(page.locator('.sh-cell-selected')).to_have_count(98)
    go('D1')
    page.keyboard.press('Control+Space')
    expect(page.locator('.sh-cell-selected')).to_have_count(7)
    go('D1')
    page.keyboard.press('F8')
    expect(page.get_by_text('F8 replaces Alt here.', exact=False)).to_be_visible()
    page.keyboard.press('Escape')

    # Hold the first autosave while another edit is made to the same row.
    held, posted = [], []

    def slow(route):
        posted.append(route.request.post_data_json)
        if len(posted) == 1:
            held.append(route)
        else:
            route.continue_()

    page.route('**/api/internal/store-hours/review', slow)
    edit('D1', 'First autosave')
    expect(page.locator('#sheet-save-state')).to_have_text('Saving...', timeout=10000)
    page.wait_for_timeout(100)
    assert held
    edit('D1', 'Newest autosave')
    go('E2')
    held[0].continue_()
    saved()
    assert len(posted) == 2 and posted[1]['revision'] == posted[0]['revision'] + 1
    assert posted[1]['cell_overrides']['employee'] == 'Newest autosave'
    expect(cell('D1')).to_have_text('NEWEST AUTOSAVE')
    expect(page.locator('#sh-grid-address')).to_have_value('E2')
    expect(cell('E2')).to_be_focused()
    page.unroute('**/api/internal/store-hours/review', slow)
    # Undo after autosave creates another saved version, then redo restores it.
    page.keyboard.press('Control+z')
    expect(cell('D1')).to_have_text('FIRST AUTOSAVE')
    saved()
    page.keyboard.press('Control+y')
    expect(cell('D1')).to_have_text('NEWEST AUTOSAVE')
    saved()

    # Failed saves preserve the draft and expose a usable retry.
    page.route('**/api/internal/store-hours/review', lambda route: route.fulfill(status=503, json={'message':'Temporary test outage'}))
    edit('D2', 'Retry retained')
    expect(page.locator('#sheet-save-state')).to_have_text('Not saved - retry', timeout=10000)
    expect(cell('D2')).to_have_text('RETRY RETAINED')
    page.unroute('**/api/internal/store-hours/review')
    page.locator('#sheet-save').click()
    saved()
    page.reload()
    expect(cell('D1')).to_have_text('NEWEST AUTOSAVE')
    expect(cell('D2')).to_have_text('RETRY RETAINED')

    # Cut is a deferred move; Escape cancels it without changing the source.
    go('D1')
    page.keyboard.press('Control+x')
    outline = page.locator('.sh-clipboard-outline')
    expect(outline).to_be_visible()
    expect(outline).to_have_attribute('data-operation', 'cut')
    expect(cell('D1')).to_have_text('NEWEST AUTOSAVE')
    page.keyboard.press('ArrowDown')
    expect(outline).to_be_visible()
    page.keyboard.press('Escape')
    expect(outline).to_be_hidden()
    expect(cell('D1')).to_have_text('NEWEST AUTOSAVE')
    go('D1')
    page.keyboard.press('Control+x')
    go('D2')
    page.keyboard.press('Control+v')
    expect(cell('D2')).to_have_text('NEWEST AUTOSAVE')
    expect(cell('D1')).not_to_have_text('NEWEST AUTOSAVE')
    expect(outline).to_be_hidden()
    page.keyboard.press('Control+z')
    expect(cell('D1')).to_have_text('NEWEST AUTOSAVE')
    expect(cell('D2')).to_have_text('RETRY RETAINED')
    saved()
    go('D1:D2')
    page.keyboard.press('Control+c')
    expect(outline).to_have_attribute('data-operation', 'copy')
    page.keyboard.press('ArrowRight')
    expect(outline).to_be_visible()
    page.screenshot(path=str(ROOT/'test-results/spreadsheet-excel-selection.png'), full_page=True)
    page.keyboard.press('Escape')

    # Clicking another cell commits the value bar to its original cell.
    go('D1')
    page.locator('#sheet-value').fill('Value bar autosave')
    cell('D2').click()
    expect(cell('D1')).to_have_text('VALUE BAR AUTOSAVE')
    expect(cell('D2')).to_have_text('RETRY RETAINED')
    saved()
    page.locator('#sheet-value').fill('Cancelled value')
    page.locator('#sheet-value').press('Escape')
    expect(cell('D2')).to_have_text('RETRY RETAINED')

    # Save pending edits before switching dates. AMQ fixture has real daily rows.
    edit('D1', 'Saved before changing dates')
    page.locator('#sheet-period-button').click()
    page.get_by_role('button', name='Oct 19, 2026', exact=True).click()
    page.get_by_role('button', name='Apply dates', exact=True).click()
    expect(page.locator('#sheet-period-button')).to_have_text('2026-10-19')
    assert 'start=2026-10-19' in page.url
    page.reload()
    expect(page.locator('#sheet-period-button')).to_have_text('2026-10-19')
    page.locator('#sheet-filter-toggle').click()
    page.locator('#sheet-dealer').select_option('AMQ')
    expect(page.locator('#sheet-row-count')).to_contain_text('1 row')
    expect(cell('A1')).to_contain_text('Oct 19, 2026')
    page.locator('#sheet-filter-toggle').click()
    page.locator('#sheet-period-button').click()
    page.get_by_label('Selection', exact=True).select_option('range')
    page.get_by_role('button', name='Oct 1, 2026', exact=True).click()
    page.get_by_role('button', name='Oct 19, 2026', exact=True).click()
    page.screenshot(path=str(ROOT/'test-results/spreadsheet-excel-calendar.png'), full_page=True)
    page.get_by_role('button', name='Apply dates', exact=True).click()
    expect(page.locator('#sheet-row-count')).to_contain_text('19 rows')
    page.locator('#sheet-period-button').click()
    page.get_by_role('button', name='Previous calendar month').click()
    page.get_by_label('Selection', exact=True).select_option('day')
    page.get_by_role('button', name='Sep 15, 2026', exact=True).click()
    page.get_by_role('button', name='Apply dates', exact=True).click()
    expect(cell('A1')).to_contain_text('Sep 15, 2026')
    page.set_viewport_size({'width':390, 'height':844})
    expect(page.locator('#sheet-period-button')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(ROOT/'test-results/spreadsheet-excel-mobile.png'), full_page=True)
    print('Autosave checks passed: concurrent edits, retry, persisted undo/redo, no reload, row/column shortcuts, green copy/cut, historical calendar, mobile.')


if __name__ == '__main__':
    main(check, spreadsheet=True)
