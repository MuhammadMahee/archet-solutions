"""All-column edits, corrections, undo, persistence, history, and exports."""
from pathlib import Path

from openpyxl import load_workbook
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

    values = ['10/19/2026','RENO','Corrected Store','Corrected Employee','Reviewed',
              '9:30 AM','9:32 AM','9:29 AM','Excused','7:30 PM','7:31 PM','7:32 PM','Verified','-$25.50']
    for col, value in zip('ABCDEFGHIJKLMN', values):
        expect(cell(col+'1')).to_have_attribute('aria-readonly','false')
        edit(col+'1', value)
    expect(cell('A1')).to_contain_text('Oct 19, 2026')
    expect(cell('D1')).to_contain_text('Corrected Store')
    expect(cell('E1')).to_have_text('Corrected Employee')
    expect(cell('J1')).to_have_text('Excused')
    expect(cell('I1')).to_have_text('9:29:00 AM')
    expect(cell('M1')).to_have_text('7:32:00 PM')
    expect(cell('O1')).to_have_text('-$25.50')
    page.keyboard.press('Control+z')
    expect(cell('O1')).to_have_text('$0')
    page.keyboard.press('Control+y')
    expect(cell('O1')).to_have_text('-$25.50')

    # One rectangular paste can contain every column type and remains atomic.
    go('A2')
    page.evaluate('(text)=>navigator.clipboard.writeText(text)', '\t'.join(values))
    page.keyboard.press('Control+v')
    expect(cell('E2')).to_have_text('Corrected Employee')
    expect(cell('O2')).to_have_text('-$25.50')
    page.keyboard.press('Control+z')
    expect(cell('E2')).to_have_text('Closing Employee')
    go('N2')
    page.evaluate('(text)=>navigator.clipboard.writeText(text)', 'Changed\tinvalid money')
    page.keyboard.press('Control+v')
    expect(page.locator('#sh-message')).to_contain_text('Nothing pasted')
    expect(cell('N2')).to_have_text('Pending camera review')

    # Undo a reset restores the correction; redo removes it again.
    go('I1')
    page.keyboard.press('F8')
    page.keyboard.press('u')
    expect(cell('I1')).to_have_text('10:02:00 AM')
    expect(cell('I1')).not_to_have_class('sh-cell-corrected')
    page.keyboard.press('Control+z')
    expect(cell('I1')).to_have_text('9:29:00 AM')
    go('O1')
    page.keyboard.press('Control+s')
    expect(page.locator('#sh-unsaved')).to_be_empty()
    expect(page.locator('#sh-message')).to_contain_text('Camera review saved')
    page.reload()
    expect(cell('E1')).to_have_text('Corrected Employee')
    expect(cell('O1')).to_have_text('-$25.50')
    expect(cell('J1')).to_have_text('Excused')
    page.locator('#sh-history').click()
    page.locator('#sh-history-list summary').first.click()
    expect(page.locator('#sh-history-list')).to_contain_text('Corrected Employee')
    expect(page.locator('#sh-history-list')).to_contain_text('Excused')
    page.locator('#sh-history-close').click()
    page.locator('#sh-switch').click()
    expect(cell('O1')).to_have_text('-$25.50')
    with page.expect_download() as download:
        page.locator('#sh-excel').click()
    path = ROOT/'test-results/store-hours-all-cells.xlsx'
    download.value.save_as(str(path))
    book = load_workbook(path)
    exported = next(row for row in book.active.iter_rows(values_only=True) if 'Corrected Employee' in row)
    assert exported[2:5] == ('Corrected Store','Corrected Employee','Reviewed')
    assert exported[13] == -25.5
    page.locator('#sh-copy').click()
    expect(page.locator('#sh-message')).to_contain_text('Snapshot copied')
    page.locator('#sh-switch').click()
    go('A1:O1')
    page.keyboard.press('F8')
    page.keyboard.press('u')
    expect(cell('E1')).to_have_text('Opening Employee')
    expect(cell('J1')).to_have_text('Pending camera review')
    expect(cell('O1')).to_have_text('Pending')
    page.keyboard.press('Control+s')
    expect(page.locator('#sh-message')).to_contain_text('Camera review saved')
    page.reload()
    expect(cell('E1')).to_have_text('Opening Employee')
    expect(cell('A1')).to_contain_text('Oct 20, 2026')
    print('All-column browser checks passed: edit, paste, validation, undo, reset, save, history, snapshot, Excel.')


if __name__ == '__main__':
    main(check)
