module.exports = async function({browser, act, assert, width}) {
  const ctx = await act(()=>browser.newContext({viewport:{width,height:900},isMobile:true,hasTouch:true}));
  const p = await act(()=>ctx.newPage());
  const faults=[];
  p.on('pageerror',error=>faults.push(String(error)));
  const inspect = async () => {
    const data=await act(()=>p.evaluate(()=>{
      const visible = e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const buttons=[...document.querySelectorAll('button,input,textarea')].filter(visible).filter(e=>!e.closest('dialog')||e.closest('dialog').open);
      return {
        overflow:document.documentElement.scrollWidth>innerWidth,
        small:buttons.filter(e=>{const r=e.getBoundingClientRect();return r.width<44 || r.height<44;}).map(e=>({id:e.id,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height})),
        wrapped:buttons.filter(e=>e.tagName==='BUTTON').filter(e=>[...e.childNodes].some(node=>{
          if(node.nodeType!==Node.TEXT_NODE||!node.textContent.trim()) return false;
          const range=document.createRange();range.selectNodeContents(node);
          return new Set([...range.getClientRects()].map(r=>Math.round(r.top))).size>1;
        })).map(e=>e.id),
      };
    }));
    assert.equal(data.overflow,false,JSON.stringify(data));
    assert.deepEqual(data.small,[],JSON.stringify(data));
    assert.deepEqual(data.wrapped,[],JSON.stringify(data));
    return data;
  };
  try {
    await act(()=>p.goto('http://127.0.0.1:7656'));
    await act(()=>p.waitForFunction(()=>!document.querySelector('#send').disabled));
    await inspect();
    await act(()=>p.screenshot({path:'D:/Work/Projects/ai-advent-challenge/swarm-report/goost-mobile-'+width+'.png',fullPage:true}));
    await act(()=>p.locator('#open-drawer').click());
    assert(await act(()=>p.locator('#drawer').evaluate(e=>e.open)));
    await inspect();
    await act(()=>p.locator('#close-drawer').click());
    assert.equal(await act(()=>p.evaluate(()=>document.activeElement.id)),'open-drawer');
    await act(()=>p.locator('#open-drawer').click());
    await act(()=>p.keyboard.press('Escape'));
    assert.equal(await act(()=>p.locator('#drawer').evaluate(e=>e.open)),false);
    assert.equal(await act(()=>p.evaluate(()=>document.activeElement.id)),'open-drawer');
    await act(()=>p.locator('#open-drawer').click());
    await act(()=>p.locator('[data-action]').click());
    await inspect();
    await act(()=>p.locator('#cancel-manage').click());
    assert.deepEqual(faults,[]);
    return {width,result:'PASS'};
  } finally {await act(()=>ctx.close());}
};
