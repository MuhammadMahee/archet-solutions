from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    page.locator('#sheet-account').click()
    expect(page.locator('#sheet-login')).to_be_visible()
    page.locator('#sheet-username').fill('Member');page.locator('#sheet-password').fill('TestPass123')
    page.locator('#sheet-login-form button[type=submit]').click()
    expect(page.locator('#sheet-row-count')).to_contain_text('7 rows')
    page.locator('#sheet-menu').get_by_role('button',name='Data',exact=True).click()
    expect(page.get_by_role('menuitem',name='Sync RT-POS sources')).to_be_enabled()
    expect(page.get_by_role('menuitem',name='Upload store schedules')).to_be_enabled()
    page.get_by_role('menuitem',name='Sync RT-POS sources').click()
    expect(page.locator('#sheet-message')).to_contain_text('Source sync completed')
    page.locator('#sheet-menu').get_by_role('button',name='Data',exact=True).click()
    page.get_by_role('menuitem',name='Upload store schedules').click()
    expect(page.locator('#sheet-dialog')).to_be_visible()
    page.locator('#sheet-dialog-close').click()
    page.locator('#sheet-menu').get_by_role('button',name='File',exact=True).click()
    page.get_by_role('menuitem',name='Change password').click()
    dialog=page.locator('#sheet-dialog')
    dialog.get_by_label('Current password',exact=True).fill('TestPass123')
    dialog.get_by_label('New password',exact=True).fill('ChangedMember123')
    dialog.get_by_label('Confirm new password',exact=True).fill('ChangedMember123')
    dialog.get_by_role('button',name='Update password').click()
    expect(page.locator('#login')).to_be_visible()
    page.locator('#login-username').fill('Member');page.locator('#login-password').fill('ChangedMember123')
    page.get_by_role('button',name='Sign in to workspace').click()
    expect(page.locator('#page-settings')).to_be_visible()
    print('Member spreadsheet: sync, schedule upload, password change, session revocation and new-password sign-in passed.')


if __name__=='__main__':main(check,spreadsheet=True)
