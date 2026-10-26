"""Spreadsheet-only navigation and schedule upload using isolated API fixtures."""
from datetime import time
from playwright.sync_api import expect
from browser_store_hours import main
from test_store_hours_directory import workbook


def check(page):
    origin=page.url.split('/spreadsheet')[0]
    page.goto(origin+'/internal#settings')
    expect(page.locator('#workspace')).to_be_visible()
    expect(page.locator('[data-page="storehours"], [data-page="storehoursreport"]')).to_have_count(0)
    expect(page.locator('#page-storehours, #page-storehoursreport')).to_have_count(0)
    page.get_by_role('button',name='Opening / Closing Spreadsheet').click()
    expect(page).to_have_url(origin+'/spreadsheet?start=2026-10-20&end=2026-10-20')
    expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    for old_page in ('storehours','storehoursreport'):
        page.goto(origin+'/internal#'+old_page)
        expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
        assert '/spreadsheet' in page.url
    page.get_by_role('button',name='Data',exact=True).click()
    page.get_by_role('menuitem',name='Upload store schedules').click()
    expect(page.locator('#sheet-dialog-title')).to_have_text('Upload store schedules')
    apply=page.get_by_role('button',name='Apply schedules',exact=True)
    expect(apply).to_be_disabled()
    file=page.get_by_label('Schedule workbook',exact=True)
    file.set_input_files({'name':'bad.txt','mimeType':'text/plain','buffer':b'bad'})
    expect(page.locator('#sheet-dialog-content')).to_contain_text('Choose an .xlsx workbook')
    expect(apply).to_be_disabled()
    file.set_input_files({'name':'schedule.xlsx','mimeType':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','buffer':workbook(store='FUTURE STORE',opening=time(22))})
    expect(page.get_by_role('table',name='Schedule preview')).to_contain_text('FUTURE STORE')
    expect(page.locator('#sheet-dialog-content')).to_contain_text('Connect opening times corrected')
    expect(apply).to_be_enabled()
    page.set_viewport_size({'width':390,'height':844})
    box=page.locator('#sheet-dialog').bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=390
    apply.click()
    expect(page.locator('#sheet-dialog')).not_to_be_visible()
    expect(page.locator('#sheet-message')).to_contain_text('Schedules saved for 1 store')
    expect(page.locator('#sh-table')).to_contain_text('FUTURE STORE')
    print('Verified spreadsheet-only navigation, old bookmark redirects, workbook validation, preview/correction, apply, and mobile upload dialog.')


if __name__=='__main__':main(check,spreadsheet=True)
