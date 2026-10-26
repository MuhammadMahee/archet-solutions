"""Selection-aware structural shortcuts, persistent removal, restoration, and history."""
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    def cell(address):return page.locator(f'#sh-table [data-address="{address}"]')
    def go(address):
        page.locator('#sh-grid-address').fill(address);page.locator('#sh-grid-address').press('Enter')
    def restore_all():
        page.get_by_role('button',name='Edit',exact=True).click()
        page.get_by_role('menuitem',name='Restore removed rows',exact=True).click()
        expect(page.locator('#sheet-dialog-title')).to_have_text('Restore removed rows')
        for checkbox in page.locator('#sheet-dialog input[type=checkbox]').all():checkbox.check()
        page.get_by_role('button',name='Restore rows',exact=True).click()
        expect(page.locator('#sheet-dialog')).not_to_be_visible()

    go('D1');page.keyboard.press('Shift+Space');page.keyboard.press('Control+Shift+=')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Add employee row')
    expect(page.get_by_label('Date',exact=True)).to_have_value('2026-10-20')
    assert 'Connect' in page.get_by_label('Store',exact=True).input_value()
    page.get_by_role('button',name='Cancel',exact=True).click()
    # Editing immediately before removal must save first and use the new revision.
    go('D1');page.keyboard.press('F2')
    page.get_by_role('textbox',name='Edit D1',exact=True).fill('Row to remove')
    page.keyboard.press('Enter');go('D1');page.keyboard.press('Shift+Space');page.keyboard.press('Control+-')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Remove 1 row')
    expect(page.locator('#sheet-dialog-content')).to_contain_text('ROW TO REMOVE')
    page.get_by_role('button',name='Remove rows',exact=True).click()
    expect(page.locator('#sheet-row-count')).to_contain_text('6 rows')
    page.reload();expect(page.locator('#sheet-row-count')).to_contain_text('6 rows')
    page.locator('#sh-history').click()
    page.locator('#sh-history-list summary').first.click()
    expect(page.locator('#sh-history-list')).to_contain_text('Removed (restorable)')
    page.locator('#sh-history-close').click()
    restore_all();expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    expect(cell('D1')).to_have_text('ROW TO REMOVE')
    # Shift-clicking row numbers selects multiple complete rows.
    page.locator('[data-sheet-row="0"]').click()
    page.locator('[data-sheet-row="1"]').click(modifiers=['Shift'])
    page.keyboard.press('Control+-')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Remove 2 rows')
    page.get_by_role('button',name='Remove rows',exact=True).click()
    expect(page.locator('#sheet-row-count')).to_contain_text('5 rows')
    restore_all();expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    # Full-column shortcuts retain column behavior and default protection.
    go('D1');page.keyboard.press('Control+Space');page.keyboard.press('Control+-')
    expect(page.locator('#sheet-message')).to_contain_text('Default columns are protected')
    page.keyboard.press('Control+=')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Add a custom column')
    page.get_by_label('Column name',exact=True).fill('Structure notes')
    page.get_by_role('button',name='Save column',exact=True).click()
    expect(cell('O7')).to_be_focused()
    page.keyboard.press('Control+Space');page.keyboard.press('Control+-')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Remove custom column')
    page.get_by_role('button',name='Remove column',exact=True).click()
    expect(page.locator('#sh-table thead')).not_to_contain_text('Structure notes')
    # One visible row must not make a column selection look like a row selection.
    page.locator('#sheet-filter-toggle').click();page.locator('#sheet-search').fill('Closing Employee')
    expect(page.locator('#sheet-row-count')).to_contain_text('1 row')
    go('D1');page.keyboard.press('Control+Space');page.keyboard.press('Control+=')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Add a custom column')
    page.get_by_role('button',name='Cancel',exact=True).click()
    go('D1');page.keyboard.press('Shift+Space');page.keyboard.press('Control+=')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Add employee row')
    page.get_by_role('button',name='Cancel',exact=True).click()
    go('D1');page.keyboard.press('Shift+Space');page.keyboard.press('Control+a');page.keyboard.press('Control+-')
    expect(page.locator('#sheet-message')).to_contain_text('Select row numbers or column headings')
    expect(page.locator('#sheet-dialog')).not_to_be_visible()
    print('Structure checks passed: row/column shortcut routing, store/date defaults, save-before-remove, durable removal, restore, audit history, multiple rows, protected columns, single-row filters.')


if __name__=='__main__':main(check,spreadsheet=True)
