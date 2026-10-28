"""Persisted font and border formatting, employee uppercase, and styled exports."""
from pathlib import Path
from openpyxl import load_workbook
from playwright.sync_api import expect
from browser_store_hours import main

ROOT=Path(__file__).resolve().parents[1]


def check(page):
    def cell(address): return page.locator(f'#sh-table [data-address="{address}"]')
    def go(address):
        page.locator('#sh-grid-address').fill(address)
        page.locator('#sh-grid-address').press('Enter')
    def saved(): expect(page.locator('#sheet-save-state')).to_have_text('All changes saved',timeout=15000)
    def borders(name):
        page.locator('#sheet-borders').click()
        page.get_by_label('Line style',exact=True).select_option('medium')
        page.get_by_label('Border color',exact=True).fill('#123456')
        page.get_by_role('button',name=name,exact=True).click()

    expect(cell('E1')).to_have_text('OPENING EMPLOYEE')
    expect(page.locator('#sheet-font-family option')).to_have_count(12)
    go('E1:F2')
    page.locator('#sheet-font-family').select_option('Calibri')
    expect(cell('E1')).to_have_css('font-family','Calibri, Arial, sans-serif')
    expect(cell('F2')).to_have_css('font-family','Calibri, Arial, sans-serif')
    borders('Outer borders')
    expect(cell('E1')).to_have_css('border-left-width','2px')
    expect(cell('E1')).to_have_css('border-top-color','rgb(18, 52, 86)')
    expect(cell('E1')).to_have_css('border-bottom-width','1px')
    expect(cell('F2')).to_have_css('border-bottom-width','2px')
    expect(cell('F2')).to_have_css('border-right-width','2px')
    page.keyboard.press('Control+z')
    expect(cell('E1')).to_have_css('border-left-width','0px')
    expect(cell('E1')).to_have_css('font-family','Calibri, Arial, sans-serif')
    page.keyboard.press('Control+y')
    expect(cell('E1')).to_have_css('border-left-width','2px')
    borders('Inner borders')
    expect(cell('E1')).to_have_css('border-right-width','2px')
    expect(cell('E1')).to_have_css('border-bottom-width','2px')
    borders('No borders')
    expect(cell('E1')).to_have_css('border-left-style','none')
    expect(cell('F2')).to_have_css('border-bottom-style','none')
    page.keyboard.press('Control+z')
    expect(cell('E1')).to_have_css('border-left-width','2px')
    saved()
    go('E1')
    page.keyboard.press('F2')
    page.get_by_role('textbox',name='Edit E1',exact=True).fill('Jane Doe')
    page.keyboard.press('Enter')
    expect(cell('E1')).to_have_text('JANE DOE')
    saved()
    page.reload()
    expect(cell('E1')).to_have_text('JANE DOE')
    expect(cell('E1')).to_have_css('font-family','Calibri, Arial, sans-serif')
    expect(cell('E1')).to_have_css('border-left-width','2px')
    go('E1')
    page.keyboard.press('Control+c')
    assert page.evaluate('navigator.clipboard.readText()')=='JANE DOE'
    page.keyboard.press('Escape')
    # Snapshot uses uppercase names while preserving the stored source spelling.
    captured=page.evaluate('''() => {
      const values=[],original=CanvasRenderingContext2D.prototype.fillText;
      CanvasRenderingContext2D.prototype.fillText=function(value,...args){values.push(value);return original.call(this,value,...args)};
      try { storeHoursSnapshot.render({rows:[{employee:'Jane Doe'}],start:'2026-10-20',end:'2026-10-20',coverage:{complete:0,expected:1}}); }
      finally {CanvasRenderingContext2D.prototype.fillText=original;}
      return values;
    }''')
    assert 'JANE DOE' in captured
    page.get_by_role('button',name='File',exact=True).click()
    page.get_by_role('menuitem',name='Download Excel',exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('button',name='Download Excel',exact=True).click()
    path=ROOT/'test-results/spreadsheet-fonts-borders.xlsx'
    download.value.save_as(str(path))
    book=load_workbook(path)
    assert book.active['E3'].value=='JANE DOE'
    assert book.active['E3'].font.name=='Calibri'
    assert book.active['E3'].border.left.style=='medium'
    assert book.active['E3'].border.left.color.rgb=='00123456'
    go('E1:F2')
    page.locator('#sheet-clear-format').click()
    expect(cell('E1')).to_have_css('font-family','Arial')
    expect(cell('E1')).to_have_css('border-left-width','0px')
    expect(cell('E1')).to_have_text('JANE DOE')
    page.keyboard.press('Control+z')
    saved()
    page.screenshot(path=str(ROOT/'test-results/spreadsheet-fonts-borders.png'),full_page=True)
    print('Style checks passed: font selection, range edges, inner/no borders, undo/redo, autosave, reload, uppercase names, clipboard, snapshot, Excel, clear formatting.')


if __name__=='__main__':main(check,spreadsheet=True)
