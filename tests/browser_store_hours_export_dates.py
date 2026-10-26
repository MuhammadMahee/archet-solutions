"""Date confirmation, validation, save-before-export, and download retry."""
from urllib.parse import parse_qs, urlparse
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    requests=[]
    page.on('request',lambda request:requests.append(request.url))
    def open_download():
        page.get_by_role('button',name='File',exact=True).click()
        page.get_by_role('menuitem',name='Download Excel',exact=True).click()
        expect(page.locator('#sheet-dialog-title')).to_have_text('Download Excel')
    def exports():return [url for url in requests if '/sheet/export?' in url]

    original=page.url
    open_download()
    expect(page.get_by_label('From date',exact=True)).to_have_value('2026-10-20')
    expect(page.get_by_label('To date',exact=True)).to_have_value('2026-10-20')
    expect(page.get_by_label('Selection',exact=True)).to_have_value('range')
    page.get_by_role('button',name='Cancel',exact=True).click()
    assert not exports()
    # A download should include the latest edit and preserve current column filters.
    page.locator('#sh-grid-address').fill('D1');page.locator('#sh-grid-address').press('Enter')
    page.keyboard.press('F2');page.get_by_role('textbox',name='Edit D1',exact=True).fill('Export employee');page.keyboard.press('Enter')
    page.get_by_role('button',name='Filter Employee column employee',exact=True).click()
    page.get_by_label('Text contains',exact=True).fill('Export')
    page.get_by_role('button',name='Apply filter',exact=True).click()
    open_download()
    start=page.get_by_label('From date',exact=True);end=page.get_by_label('To date',exact=True)
    submit=page.get_by_role('button',name='Download Excel',exact=True)
    start.fill('2026-10-19');end.fill('2026-10-01');submit.click()
    expect(page.locator('#sheet-dialog-content [role=alert]')).to_contain_text('Choose a valid period')
    assert not exports()
    end.fill('2026-10-21');submit.click()
    expect(page.locator('#sheet-dialog-content [role=alert]')).to_contain_text('Choose a valid period')
    assert not exports()
    start.fill('2026-10-01');end.fill('2026-10-10')
    # Keep the picker open on a server error so the user can retry.
    page.route('**/store-hours/sheet/export?*',lambda route:route.fulfill(status=503,json={'message':'Export temporarily unavailable'}),times=1)
    submit.click()
    expect(page.locator('#sheet-dialog-content [role=alert]')).to_have_text('Export temporarily unavailable')
    expect(submit).to_be_enabled()
    with page.expect_download() as download:submit.click()
    assert download.value.suggested_filename=='opening-closing-sheet-2026-10-01-2026-10-10.xlsx'
    assert download.value.failure() is None
    expect(page.locator('#sheet-dialog')).not_to_be_visible()
    assert page.url==original
    expect(page.locator('#sheet-period-button')).to_have_text('2026-10-20')
    query=parse_qs(urlparse(exports()[-1]).query)
    assert query['start']==['2026-10-01'] and query['end']==['2026-10-10']
    assert 'Export' in query['filters'][0]
    assert next(i for i,url in enumerate(requests) if '/store-hours/review' in url)<next(i for i,url in enumerate(requests) if '/sheet/export?' in url)
    print('Verified export date prompt, cancel, invalid dates, retained filters/period, save-before-export, retry, and selected-range filename.')


if __name__=='__main__':main(check,spreadsheet=True)
