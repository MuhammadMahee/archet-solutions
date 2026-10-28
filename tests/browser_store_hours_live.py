"""Two authenticated sessions edit the shared sheet without refresh or lost updates."""
from datetime import datetime, timezone
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    context=page.context.browser.new_context(viewport={'width':1100,'height':850})
    peer=context.new_page();errors=[];peer.on('pageerror',lambda error:errors.append(str(error)))
    peer.clock.set_fixed_time(datetime(2026,10,20,17,tzinfo=timezone.utc))
    peer.goto(page.url)
    peer.locator('#sheet-username').fill('Member');peer.locator('#sheet-password').fill('TestPass123')
    peer.locator('#sheet-login-form button[type=submit]').click()
    expect(peer.locator('#sheet-row-count')).to_contain_text('7 rows')
    def go(tab,address):
        tab.locator('#sh-grid-address').fill(address);tab.locator('#sh-grid-address').press('Enter')
    def cell(tab,address):return tab.locator(f'#sh-table [data-address="{address}"]')
    def edit(tab,address,value,commit=True):
        go(tab,address);tab.keyboard.press('F2');tab.get_by_role('textbox',name='Edit '+address,exact=True).fill(value)
        if commit:tab.keyboard.press('Enter')
    def saved(tab):expect(tab.locator('#sheet-save-state')).to_have_text('All changes saved',timeout=15000)
    # Updating another tab must preserve this tab's selection and viewport.
    go(page,'G2');scroll=page.locator('.sheet-grid-wrap').evaluate('el=>el.scrollLeft')
    edit(peer,'D1','Live employee');saved(peer)
    expect(cell(page,'D1')).to_have_text('LIVE EMPLOYEE',timeout=15000)
    expect(cell(page,'G2')).to_be_focused()
    assert abs(page.locator('.sheet-grid-wrap').evaluate('el=>el.scrollLeft')-scroll)<1
    # Idle ticks query the small change token and leave the DOM untouched.
    checks=[];page.on('request',lambda request:checks.append(request.url) if '/sheet/presence' in request.url else None)
    cell(page,'D1').evaluate("el=>el.dataset.liveProbe='kept'")
    page.wait_for_timeout(2300)
    assert len(checks)>=2,checks
    expect(cell(page,'D1')).to_have_attribute('data-live-probe','kept')
    # Do not interrupt typing; merge simultaneous changes to different cells in one row.
    edit(peer,'G1','10:14 AM',commit=False)
    edit(page,'D1','Primary name');saved(page)
    expect(peer.locator('#sheet-live-state')).to_have_text('Updates waiting',timeout=15000)
    expect(peer.get_by_role('textbox',name='Edit G1',exact=True)).to_have_value('10:14 AM')
    peer.keyboard.press('Enter');saved(peer)
    expect(cell(peer,'D1')).to_have_text('PRIMARY NAME')
    expect(cell(page,'G1')).to_contain_text('10:14',timeout=15000)
    # Same-cell edits require explicit resolution, rather than last-write-wins.
    edit(peer,'D1','Peer draft',commit=False)
    edit(page,'D1','Latest saved');saved(page)
    peer.keyboard.press('Enter')
    expect(peer.locator('#sheet-resolve-conflict')).to_be_visible(timeout=15000)
    peer.locator('#sheet-resolve-conflict').click()
    expect(peer.locator('#sheet-dialog-content')).to_contain_text('PEER DRAFT')
    expect(peer.locator('#sheet-dialog-content')).to_contain_text('LATEST SAVED')
    peer.get_by_role('button',name='Use latest values',exact=True).click();saved(peer)
    expect(cell(peer,'D1')).to_have_text('LATEST SAVED')
    edit(peer,'D1','Chosen local',commit=False)
    edit(page,'D1','Other saved');saved(page)
    peer.keyboard.press('Enter');expect(peer.locator('#sheet-resolve-conflict')).to_be_visible(timeout=15000)
    peer.locator('#sheet-resolve-conflict').click();peer.get_by_role('button',name='Keep my values',exact=True).click();saved(peer)
    expect(cell(page,'D1')).to_have_text('CHOSEN LOCAL',timeout=15000)
    expect(cell(page,'G1')).to_contain_text('10:14')
    # Shared column changes arrive without resetting the selected employee cell.
    go(page,'D1');peer.locator('#sheet-add-column').click()
    peer.get_by_label('Column name',exact=True).fill('Live notes')
    peer.get_by_role('button',name='Save column',exact=True).click()
    expect(page.locator('#sh-table thead')).to_contain_text('Live notes',timeout=15000)
    expect(cell(page,'D1')).to_be_focused()
    # Network errors back off and recover; existing contents remain visible.
    page.route('**/sheet/presence',lambda route:route.abort())
    expect(page.locator('#sheet-live-state')).to_have_text('Reconnecting...',timeout=15000)
    edit(peer,'D2','After reconnect');saved(peer)
    page.unroute('**/sheet/presence')
    expect(cell(page,'D2')).to_have_text('AFTER RECONNECT',timeout=15000)
    expect(page.locator('#sheet-live-state')).to_have_text('Live')
    # Polling our own save must not clear undo or move focus.
    before=cell(page,'D3').inner_text();edit(page,'D3','Own saved edit');saved(page)
    page.wait_for_timeout(2200);page.keyboard.press('Control+z');saved(page)
    expect(cell(page,'D3')).to_have_text(before)
    # A delayed live response for the old period must never replace a newer view.
    held=[]
    def hold_old(route):
        if not held:held.append((route,route.fetch()))
        else:route.continue_()
    page.route('**/store-hours/sheet?*',hold_old)
    edit(peer,'D2','Delayed live update');saved(peer)
    for _ in range(50):
        if held:break
        page.wait_for_timeout(100)
    assert held
    page.locator('#sheet-period-button').click()
    page.get_by_label('From date',exact=True).fill('2026-10-19')
    page.get_by_role('button',name='Apply dates',exact=True).click()
    expect(page.locator('#sheet-period-button')).to_have_text('2026-10-19')
    held[0][0].fulfill(response=held[0][1]);page.unroute('**/store-hours/sheet?*')
    page.wait_for_timeout(1200)
    expect(page.locator('#sheet-period-button')).to_have_text('2026-10-19')
    assert 'start=2026-10-19' in page.url
    assert not errors,errors
    context.close()
    print('Live checks passed: two users, one-second checks, idle DOM stability, selection/scroll, active editor, same-row merge, both conflict choices, shared columns, network recovery, own-save undo, stale responses.')


if __name__=='__main__':main(check,spreadsheet=True)
