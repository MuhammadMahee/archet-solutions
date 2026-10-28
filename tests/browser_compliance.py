"""Spreadsheet validation, conditional colors, autosave and camera suggestions."""
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    origin=page.url.split('/spreadsheet')[0]
    page.goto(origin+'/compliance?start=2026-10-20&end=2026-10-20')
    expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    expect(page.locator('.sheet-heading h1')).to_contain_text('Compliance')
    assert page.locator('#sh-table thead th').count()==13
    expect(page.locator('#sh-table tbody tr').first.locator('[data-column=dealer_name]')).to_have_text('Connect')
    def edit(field,value):
        cell=page.locator('#sh-table tbody tr').first.locator('[data-column='+field+']')
        cell.dblclick()
        editor=page.locator('.sh-cell-editor')
        expect(editor).to_have_attribute('list','sh-check-options')
        editor.fill(value);editor.press('Enter')
        expect(cell).to_have_text(value)
        expect(page.locator('#sheet-save-state')).to_have_text('All changes saved')
        return cell
    for field,value,color,bg in [('store_cleaning','No','rgb(156, 0, 6)','rgb(255, 199, 206)'),('name_tag','Yes','rgb(0, 97, 0)','rgb(198, 239, 206)'),('shirt','#N/A','rgb(156, 87, 0)','rgb(255, 235, 156)')]:
        cell=edit(field,value)
        expect(cell).to_have_css('color',color);expect(cell).to_have_css('background-color',bg)
    cell=page.locator('[data-column=shoes]').first
    cell.dblclick();editor=page.locator('.sh-cell-editor');editor.fill('Maybe');editor.press('Enter')
    expect(editor).to_have_attribute('aria-invalid','true');editor.press('Escape')
    page.reload();expect(page.locator('[data-column=shirt]').first).to_have_text('#N/A')
    page.locator('#sh-history').click()
    expect(page.locator('#sh-history-list')).to_contain_text('Shirt correction')
    page.locator('#sh-history-close').click()
    page.screenshot(path='test-results/compliance-sheet.png',full_page=True)
    page.goto(origin+'/spreadsheet?start=2026-10-20&end=2026-10-20')
    cell=page.locator('[data-column=camera_in]').first
    cell.dblclick();editor=page.locator('.sh-cell-editor');editor.fill('C')
    expect(editor).to_have_attribute('list','sh-camera-options')
    expect(page.locator('#sh-camera-options option')).to_have_attribute('value','Camera Offline')
    editor.fill('Camera Offline');editor.press('Enter')
    expect(cell).to_have_text('Camera Offline')
    expect(page.locator('#sheet-save-state')).to_have_text('All changes saved')
    cell.dblclick();editor=page.locator('.sh-cell-editor');editor.fill('Invalid text');editor.press('Enter')
    expect(editor).to_have_attribute('aria-invalid','true');editor.press('Escape')
    cell.dblclick();editor=page.locator('.sh-cell-editor');editor.fill('10:00 AM');editor.press('Enter')
    expect(cell).to_contain_text('10:00:00 AM')
    print('Compliance choices, colors, autosave, history, and camera validation passed.')


if __name__=='__main__':main(check,spreadsheet=True)
