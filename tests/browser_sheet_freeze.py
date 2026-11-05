"""Frozen identity columns stay aligned while the rest of the sheet scrolls."""
from pathlib import Path
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    page.set_viewport_size({'width':1600,'height':950})
    page.emulate_media(reduced_motion='reduce')
    table=page.locator('#sh-table')
    wrap=page.locator('.sheet-grid-wrap')
    def go(address):
        page.locator('#sh-grid-address').fill(address)
        page.locator('#sh-grid-address').press('Enter')
    def positions():
        return page.locator('#sh-table tbody tr').first.locator('td').evaluate_all('(cells)=>cells.slice(0,6).map(c=>c.getBoundingClientRect().left)')
    def active_visible():
        page.wait_for_function('''() => {
            const cell=document.querySelector('.sh-cell-active'),rect=cell.getBoundingClientRect();
            const wrap=document.querySelector('.sheet-grid-wrap'),bounds=wrap.getBoundingClientRect();
            const edge=document.querySelector('tbody .sh-frozen-edge');
            const left=edge&&!cell.classList.contains('sh-frozen')?edge.getBoundingClientRect().right:bounds.left;
            return rect.left>=left-1&&rect.right<=bounds.right+1;
        }''')
    expect(page.locator('thead .sh-frozen')).to_have_count(5)
    before=positions()
    wrap.evaluate('(el)=>el.scrollLeft=700')
    after=positions()
    assert all(abs(before[i]-after[i])<1 for i in range(5)), (before,after)
    assert before[5]-after[5]>600
    for letter in 'ABCDE':
        cell=page.locator(f'[data-address="{letter}1"]')
        assert cell.evaluate('''el=>{const r=el.getBoundingClientRect();return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2).closest('td')===el;}''')
    go('E1:F2')
    page.keyboard.press('Control+c')
    wrap.evaluate('(el)=>el.scrollLeft=el.scrollWidth')
    page.wait_for_function('''()=>{
        const range=document.querySelector('.sh-clipboard-outline').getBoundingClientRect();
        const employee=document.querySelector('[data-address="E1"]').getBoundingClientRect();
        return range.width>=employee.width-1 && Math.abs(range.left-employee.left)<1;
    }''')
    go('P1');active_visible()
    left=wrap.evaluate('(el)=>el.scrollLeft')
    go('E1');active_visible()
    assert abs(wrap.evaluate('(el)=>el.scrollLeft')-left)<1
    page.emulate_media(reduced_motion='no-preference')
    assert page.evaluate('''async()=>{
        document.querySelector('.sheet-grid-wrap').scrollLeft-=100;
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        const a=document.querySelector('[data-address="E1"]').getBoundingClientRect();
        const b=document.querySelector('.sh-selection-outline').getBoundingClientRect();
        return Math.abs(a.left-b.left)<1;
    }''')
    page.emulate_media(reduced_motion='reduce')
    page.keyboard.press('F2')
    page.get_by_label('Edit E1',exact=True).fill('Frozen employee')
    page.keyboard.press('Enter')
    expect(page.locator('[data-address="E1"]')).to_have_text('FROZEN EMPLOYEE')
    go('F1');active_visible()
    page.locator('#sheet-zoom').select_option('125%')
    expect(page.locator('thead .sh-frozen')).to_have_count(5)
    go('P1');active_visible()
    page.locator('.sheet-format-bar [data-theme-toggle]').click()
    expect(page.locator('[data-address="E1"]')).to_have_css('background-color','rgb(17, 31, 48)')
    page.screenshot(path=str(Path('test-results/sheet-frozen.png').resolve()),full_page=True)
    page.locator('#sheet-zoom').select_option('100%')
    page.set_viewport_size({'width':390,'height':844})
    expect(page.locator('thead .sh-frozen')).to_have_count(0)
    go('P1');active_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.set_viewport_size({'width':1600,'height':950})
    expect(page.locator('thead .sh-frozen')).to_have_count(5)
    origin=page.url.split('/spreadsheet')[0]
    page.goto(origin+'/compliance?start=2026-10-20&end=2026-10-20')
    expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    expect(page.locator('thead .sh-frozen')).to_have_count(0)
    print('PASS: freeze through Employee, scroll, hit targets, keyboard, editing, zoom, dark mode, narrow screens, compliance unchanged.')


if __name__=='__main__':main(check,spreadsheet=True)
