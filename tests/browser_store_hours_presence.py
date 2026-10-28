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
    member_box=page.locator('.sheet-peer-selection[aria-label^="Member "]')
    admin_box=page.locator('.sheet-peer-selection[aria-label^="OtherAdmin "]')
    expect(member_box).to_have_attribute('data-peer-address','D2',timeout=15000)
    expect(admin_box).to_have_attribute('data-peer-address','G1',timeout=15000)
    assert member_box.evaluate('el=>getComputedStyle(el).borderColor')!=admin_box.evaluate('el=>getComputedStyle(el).borderColor')
    # Focus moves, but unfinished cell text is never sent to other users.
    member.keyboard.press('F2');member.get_by_role('textbox',name='Edit D2',exact=True).fill('Unfinished private text')
    expect(member_box).to_have_attribute('data-editing','true',timeout=15000)
    expect(member_box.locator('.sheet-peer-dots')).to_be_visible()
    expect(page.locator('[data-address="D2"]')).to_have_text('CLOSING EMPLOYEE')
    member.keyboard.press('Escape');expect(member_box).to_have_attribute('data-editing','false',timeout=15000)
    # Formula-bar editing also signals the same cell.
    member.locator('#sheet-value').focus()
    expect(member_box).to_have_attribute('data-editing','true',timeout=15000)
    member.locator('#sheet-value').press('Escape')
    expect(member_box).to_have_attribute('data-editing','false',timeout=15000)
    # A locally filtered row changes its address, not the identity the peer follows.
    page.locator('#sheet-filter-toggle').click();page.locator('#sheet-search').fill('Closing Employee')
    expect(page.locator('#sheet-row-count')).to_contain_text('1 row')
    expect(member_box).to_have_attribute('data-peer-address','D1',timeout=15000)
    expect(admin_box).to_have_count(0)
    expect(page.locator('.sheet-person')).to_have_count(3)
    page.locator('#sheet-search').fill('');page.locator('#sheet-filter-toggle').click()
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
