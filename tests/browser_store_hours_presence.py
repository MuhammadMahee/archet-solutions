"""Three users, colored cell identity, unfinished typing, and presence lifecycle."""
from datetime import datetime, timezone
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    contexts=[]
    def join(name):
        context=page.context.browser.new_context(viewport={'width':1200,'height':850});contexts.append(context)
        tab=context.new_page();tab.clock.set_fixed_time(datetime(2026,10,20,17,tzinfo=timezone.utc))
        tab.goto(page.url);tab.locator('#sheet-username').fill(name);tab.locator('#sheet-password').fill('TestPass123')
        tab.locator('#sheet-login-form button[type=submit]').click()
        expect(tab.locator('#sheet-row-count')).to_contain_text('7 rows')
        return tab
    def go(tab,address):
        tab.locator('#sh-grid-address').fill(address);tab.locator('#sh-grid-address').press('Enter')
    member=join('Member');admin=join('OtherAdmin')
    go(member,'D2');go(admin,'G1')
    expect(page.locator('.sheet-person')).to_have_count(3,timeout=15000)
    expect(page.locator('#sheet-presence')).to_contain_text('Mahee (you)')
    expect(page.locator('.sheet-person').last).to_contain_text('Mahee')
    expect(member.locator('.sheet-person').last).to_contain_text('Mahee',timeout=15000)
    member_box=page.locator('.sheet-peer-selection[aria-label^="Member "]')
    admin_box=page.locator('.sheet-peer-selection[aria-label^="OtherAdmin "]')
    expect(member_box).to_have_attribute('data-peer-address','D2',timeout=15000)
    expect(admin_box).to_have_attribute('data-peer-address','G1',timeout=15000)
    assert member_box.evaluate('el=>getComputedStyle(el).borderColor')!=admin_box.evaluate('el=>getComputedStyle(el).borderColor')
    # Compact initials expand on hover/focus without being recreated each heartbeat.
    label=member_box.locator('.sheet-peer-label');initial=label.locator('.sheet-peer-initial');name=label.locator('.sheet-peer-name')
    expect(initial).to_have_text('M');expect(initial).to_be_visible()
    expect(name).to_have_css('opacity','0')
    compact=label.bounding_box()['width']
    label.hover();expect(name).to_have_css('opacity','1');expect(name).to_have_text('Member')
    assert label.bounding_box()['width']>compact
    page.mouse.move(0,0);expect(name).to_have_css('opacity','0')
    label.focus();expect(name).to_have_css('opacity','1')
    page.locator('#sh-grid-address').focus();expect(name).to_have_css('opacity','0')
    expect(page.locator('#sheet-font-family')).to_have_value('Calibri')
    assert page.locator('[data-address="D2"]').evaluate('el=>getComputedStyle(el).fontFamily').startswith('Calibri')
    # Focus moves, but unfinished cell text is never sent to other users.
    member.keyboard.press('F2');member.get_by_role('textbox',name='Edit D2',exact=True).fill('Unfinished private text')
    expect(member_box).to_have_attribute('data-editing','true',timeout=15000)
    expect(member_box.locator('.sheet-peer-dots')).to_be_visible()
    expect(initial).to_be_hidden()
    expect(member_box.locator('.sheet-peer-dots')).to_have_css('font-weight','900')
    expect(page.locator('[data-address="D2"]')).to_have_text('CLOSING EMPLOYEE')
    member.keyboard.press('Escape');expect(member_box).to_have_attribute('data-editing','false',timeout=15000)
    expect(initial).to_be_visible();expect(member_box.locator('.sheet-peer-dots')).to_be_hidden()
    # Formula-bar editing also signals the same cell.
    member.locator('#sheet-value').focus()
    expect(member_box).to_have_attribute('data-editing','true',timeout=15000)
    member.locator('#sheet-value').press('Escape')
    expect(member_box).to_have_attribute('data-editing','false',timeout=15000)
    ranges=page.locator('.sheet-peer-range[aria-label^="Member "]')
    go(member,'D1');member.keyboard.press('Shift+ArrowRight');member.keyboard.press('Shift+ArrowDown')
    expect(ranges).to_have_count(1,timeout=15000)
    expect(ranges).to_have_attribute('data-peer-range','D1:E2')
    # Separate ranges remain separate; selected rows and columns cover their full extent.
    go(member,'D1:D2,F3:F4')
    expect(ranges).to_have_count(2,timeout=15000)
    expect(ranges.nth(0)).to_have_attribute('data-peer-range','D1:D2')
    expect(ranges.nth(1)).to_have_attribute('data-peer-range','F3:F4')
    go(member,'D2');member.keyboard.press('Shift+Space')
    expect(ranges).to_have_count(1,timeout=15000)
    expect(ranges).to_have_attribute('data-peer-range','A2:N2')
    go(member,'D2');member.keyboard.press('Control+Space')
    expect(ranges).to_have_attribute('data-peer-range','D1:D7',timeout=15000)
    go(member,'D1:F3')
    expect(ranges).to_have_attribute('data-peer-range','D1:F3',timeout=15000)
    # A locally filtered row changes its address, not the identity the peer follows.
    page.locator('#sheet-filter-toggle').click();page.locator('#sheet-search').fill('Closing Employee')
    expect(page.locator('#sheet-row-count')).to_contain_text('1 row')
    expect(ranges).to_have_attribute('data-peer-range','D1:F1',timeout=15000)
    # The active endpoint is hidden, but the selected visible row still shows.
    expect(member_box).to_have_count(0)
    expect(admin_box).to_have_count(0)
    expect(page.locator('.sheet-person')).to_have_count(3)
    page.locator('#sheet-search').fill('');page.locator('#sheet-filter-toggle').click()
    go(member,'D2')
    expect(ranges).to_have_count(0,timeout=15000)
    expect(member_box).to_have_attribute('data-peer-address','D2',timeout=15000)
    # Hiding a tab announces departure; showing it rejoins with a newer sequence.
    member.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true});document.dispatchEvent(new Event('visibilitychange',{bubbles:true}))")
    expect(page.locator('.sheet-person')).to_have_count(2,timeout=10000)
    expect(member_box).to_have_count(0)
    member.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false});document.dispatchEvent(new Event('visibilitychange',{bubbles:true}))")
    expect(page.locator('.sheet-person')).to_have_count(3,timeout=10000)
    expect(member_box).to_have_count(1,timeout=10000)
    # A second tab does not duplicate the person in the top strip.
    extra=member.context.new_page();extra.clock.set_fixed_time(datetime(2026,10,20,17,tzinfo=timezone.utc));extra.goto(page.url)
    expect(page.locator('.sheet-person[title="Member - 2 open tabs"]')).to_have_count(1,timeout=15000)
    expect(page.locator('.sheet-person')).to_have_count(3)
    extra.close()
    # A crashed/disconnected browser ages out even without a leave request.
    admin.route('**/sheet/presence',lambda route:route.abort())
    expect(page.locator('.sheet-person').filter(has_text='OtherAdmin')).to_have_count(0,timeout=20000)
    expect(admin_box).to_have_count(0)
    page.set_viewport_size({'width':390,'height':844})
    box=page.locator('#sheet-presence').bounding_box()
    assert box['x']>=0 and box['x']+box['width']<=390
    for context in contexts:context.close()
    print('Presence checks passed: three accounts, distinct colors, typing dots, no draft sharing, formula bar, filter identity, hidden-tab leave/rejoin, tab deduplication, expiry, mobile.')


if __name__=='__main__':main(check,spreadsheet=True)
