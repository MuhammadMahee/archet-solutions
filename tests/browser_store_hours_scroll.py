"""Offscreen columns slide into view while focus and typing remain immediate."""
from playwright.sync_api import expect
from browser_store_hours import main


def check(page):
    page.set_viewport_size({'width':1000,'height':800})
    def go(address):
        page.locator('#sh-grid-address').fill(address)
        page.locator('#sh-grid-address').press('Enter')
    def visible():
        page.wait_for_function('''() => {
          const wrap=document.querySelector('.sheet-grid-wrap'),box=wrap.getBoundingClientRect();
          const cell=document.querySelector('.sh-cell-active').getBoundingClientRect();
          const gutter=document.querySelector('#sh-table thead th').getBoundingClientRect().width;
          const outline=document.querySelector('.sh-selection-outline').getBoundingClientRect();
          return cell.left>=box.left+gutter-1 && cell.right<=box.left+wrap.clientWidth+1 && Math.abs(outline.left-cell.left)<1;
        }''')

    go('A1')
    visible()
    # Capture actual animation frames: focus changes before scrolling completes.
    result=page.evaluate('''async () => {
      const wrap=document.querySelector('.sheet-grid-wrap'),samples=[];
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));
      const immediate=wrap.scrollLeft,focus=document.activeElement.dataset.address,start=performance.now();
      await new Promise(resolve=>{function tick(now){samples.push(wrap.scrollLeft);if(now-start<300)requestAnimationFrame(tick);else resolve();}requestAnimationFrame(tick);});
      return {immediate,focus,samples};
    }''')
    assert result['focus']=='N1' and result['immediate']==0,result
    samples=result['samples'];end=samples[-1]
    assert end>500 and any(0<x<end-1 for x in samples),samples
    assert all(b>=a-1 for a,b in zip(samples,samples[1:])),samples
    visible()
    # Moving back left animates, and a reversal replaces the pending destination.
    go('A1')
    page.keyboard.press('Control+ArrowRight')
    expect(page.locator('[data-address="N1"]')).to_be_focused()
    visible()
    go('A1')
    visible()
    for _ in range(13):page.keyboard.press('ArrowRight')
    visible()
    expect(page.locator('[data-address="N1"]')).to_be_focused()
    page.locator('#sheet-zoom').select_option('125%')
    go('A1')
    visible()
    go('N1')
    visible()
    # Manual scrolling takes over instead of fighting the keyboard animation.
    result=page.evaluate('''async () => {
      const wrap=document.querySelector('.sheet-grid-wrap');
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'Home',bubbles:true}));
      wrap.dispatchEvent(new WheelEvent('wheel',{deltaX:100,bubbles:true}));wrap.scrollLeft=300;
      await new Promise(resolve=>setTimeout(resolve,250));return wrap.scrollLeft;
    }''')
    assert result==300,result
    # Starting to type must not snap the scrolling viewport to the editor.
    go('A1');visible()
    result=page.evaluate('''() => {
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));
      document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:'F2',bubbles:true}));
      return document.querySelector('.sheet-grid-wrap').scrollLeft;
    }''')
    assert result==0,result
    page.keyboard.press('Escape')
    visible()
    page.emulate_media(reduced_motion='reduce')
    go('A1')
    assert page.locator('.sheet-grid-wrap').evaluate('el=>el.scrollLeft')==0
    page.keyboard.press('End')
    visible()
    page.emulate_media(reduced_motion='no-preference')
    print('Scroll checks passed: intermediate animation frames, immediate focus, reversals, rapid arrows, zoom, manual interruption, editor focus, reduced motion.')


if __name__=='__main__':main(check,spreadsheet=True)
