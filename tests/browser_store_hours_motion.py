"""Column keyboard actions and moving selection geometry in the dedicated sheet."""
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

    def aligned():
        page.wait_for_function('''() => {
          const a=document.querySelector('.sh-selection-outline').getBoundingClientRect();
          const b=document.querySelector('.sh-cell-active').getBoundingClientRect();
          return ['left','top','width','height'].every(k=>Math.abs(a[k]-b[k])<1);
        }''')

    # The active cell changes immediately; the border takes a short animated path.
    go('D1')
    aligned()
    result = page.evaluate('''async () => {
      const border=document.querySelector('.sh-selection-outline');
      const before=border.getBoundingClientRect().left;
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));
      getComputedStyle(border).transform;
      return {focus:document.activeElement.dataset.address, before,
        animations:border.getAnimations().map(a=>a.effect.getTiming().duration)};
    }''')
    assert result['focus'] == 'E1' and 110 in result['animations'], result
    aligned()
    # Repeated moves converge to the newest cell without a queue of animations.
    for _ in range(9):
        page.keyboard.press('ArrowRight')
    expect(cell('N1')).to_be_focused()
    aligned()
    page.locator('#sheet-zoom').select_option('125%')
    aligned()
    page.set_viewport_size({'width':1100,'height':800})
    aligned()
    go('D1:D2')
    page.keyboard.press('Control+c')
    page.keyboard.press('ArrowRight')
    expect(page.locator('.sh-clipboard-outline')).to_be_visible()
    aligned()
    page.keyboard.press('Escape')
    page.emulate_media(reduced_motion='reduce')
    page.keyboard.press('ArrowDown')
    expect(page.locator('.sh-selection-outline')).to_have_css('transition-duration', '0s')
    aligned()
    page.emulate_media(reduced_motion='no-preference')

    # Ctrl+minus never offers to delete the built-in Employee column.
    go('D1')
    page.keyboard.press('Control+-')
    expect(page.locator('#sheet-message')).to_contain_text('Default columns are protected')
    expect(page.locator('#sheet-dialog')).not_to_be_visible()
    expect(cell('D1')).to_have_text('Opening Employee')
    # Main keyboard plus (Ctrl+Shift+=), Ctrl+=, and numpad plus all open insert.
    page.keyboard.press('Control+Shift+=')
    expect(page.locator('#sheet-dialog-title')).to_have_text('Add a custom column')
    page.get_by_label('Column name', exact=True).fill('Keyboard Notes')
    page.get_by_role('button', name='Save column', exact=True).click()
    expect(cell('O1')).to_be_focused()
    expect(page.locator('thead')).to_contain_text('Keyboard Notes')
    aligned()
    # Add focuses the new column, so minus immediately targets that column.
    page.keyboard.press('Control+-')
    expect(page.locator('#sheet-dialog-content')).to_contain_text('Keyboard Notes')
    page.get_by_role('button', name='Cancel', exact=True).click()
    expect(page.locator('thead')).to_contain_text('Keyboard Notes')
    go('O1')
    page.keyboard.press('Control+-')
    page.get_by_role('button', name='Remove column', exact=True).click()
    expect(page.locator('thead')).not_to_contain_text('Keyboard Notes')
    expect(cell('N1')).to_be_focused()
    aligned()
    for shortcut in ('Control+=', 'Control+NumpadAdd'):
        go('D1')
        page.keyboard.press(shortcut)
        expect(page.locator('#sheet-dialog-title')).to_have_text('Add a custom column')
        page.get_by_role('button', name='Cancel', exact=True).click()
    go('D1')
    page.keyboard.press('Control+NumpadSubtract')
    expect(page.locator('#sheet-message')).to_contain_text('Default columns are protected')
    # Browser zoom shortcuts are not hijacked while typing in an input.
    page.locator('#sheet-value').focus()
    assert page.locator('#sheet-value').evaluate('''el=>el.dispatchEvent(new KeyboardEvent('keydown',
      {key:'+',ctrlKey:true,bubbles:true,cancelable:true}))''')
    expect(page.locator('#sheet-dialog')).not_to_be_visible()
    go('D2')
    page.keyboard.press('F2')
    expect(page.locator('.sh-selection-outline')).to_be_hidden()
    page.locator('#sheet-zoom').click()
    expect(page.locator('.sh-selection-outline')).to_be_visible()
    page.keyboard.press('Escape')
    aligned()
    page.screenshot(path=str(ROOT/'test-results/spreadsheet-moving-selection.png'), full_page=True)
    print('Motion/shortcut checks passed: animated border, rapid moves, zoom, resize, reduced motion, copy outline, column add/delete, protected defaults, keyboard variants, input scoping.')


if __name__ == '__main__':
    main(check, spreadsheet=True)
