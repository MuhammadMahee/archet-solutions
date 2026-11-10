"""Source sync messages and persistent source-data warning markers in the real sheet."""
from playwright.sync_api import expect
from browser_store_hours import main
from api.store_hours import PUNCH_ORDER_WARNING


def check(page):
    def flagged_sheet(route):
        response=route.fetch();data=response.json()
        data['rows'][0]['source_warning']=PUNCH_ORDER_WARNING
        route.fulfill(response=response,json=data)
    page.route('**/api/internal/store-hours/sheet?*',flagged_sheet)
    results=[{'status':'partial','remaining':1,'pending':1,'warnings':1,'workers':[{'source':'srh','completed':1,'warnings':1}]},
             {'status':'complete','remaining':0,'pending':0,'warnings':0,'workers':[{'source':'srh','completed':1}]},
             {'status':'partial','remaining':2,'pending':0,'workers':[{'source':'srh','completed':0,'error':'source_timeout'}]},
             {'status':'busy','remaining':1,'workers':[]}]
    page.route('**/api/internal/store-hours/refresh',lambda route:route.fulfill(json=results.pop(0)))
    def sync():
        page.get_by_role('button',name='Data',exact=True).click()
        page.get_by_role('menuitem',name='Sync RT-POS sources',exact=True).click()
    sync()
    expect(page.locator('#sheet-message')).to_contain_text('Source sync completed.')
    expect(page.locator('#sheet-message')).to_contain_text('1 source punch has a clock-out before clock-in')
    expect(page.locator('#sh-table tbody th').first).to_have_attribute('title',PUNCH_ORDER_WARNING)
    sync()
    expect(page.locator('#sheet-message')).to_contain_text('2 source days could not be fetched (SRH: request timed out)')
    sync()
    expect(page.locator('#sheet-message')).to_have_text('Another source sync is running. Reload after it finishes.')
    assert not results
    print('Verified sync progress, warning persistence, failure details, and busy status.')


if __name__=='__main__':main(check,spreadsheet=True)
