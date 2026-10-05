const {chromium}=require('C:/Users/John Omest/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const fs=require('node:fs');
const http=require('node:http');
const root='D:/Work/Projects/ai-advent-challenge/';
const staticDir=root+'projects/week-2-task-2/static/';
const scenario=root+'swarm-report/goost-chat-e2e-scenario.md';
async function act(fn){execFileSync('powershell.exe',['-NoProfile','-Command','Get-Content -Raw -Encoding UTF8 "'+scenario+'"']);return await fn();}
const html=fs.readFileSync(staticDir+'index.html','utf8');
const css=fs.readFileSync(staticDir+'styles.css','utf8');
const tokens=fs.readFileSync(staticDir+'tokens.css','utf8');
const assets={'/':['index.html','text/html'],'/styles.css':['styles.css','text/css'],'/tokens.css':['tokens.css','text/css'],'/app.js':['app.js','text/javascript']};
const fixture={id:'validation-chat',title:'Проверка типографики',model:'local-fixture',busy:false,total_tokens:0,message_count:2,created_at:1,updated_at:1,messages:[{role:'user',content:'Проверка визуальных состояний'},{role:'assistant',content:('Сохранённый диалог помогает продолжить работу над задачей. Проверим длинные строки текста, контраст и доступность элементов управления. ').repeat(10)}]};
const results={source:{noBlack:!/#0b0b0b/i.test(html+css+tokens),tokenDiscipline:!/(?:#[0-9a-f]{3,8}\b|\b(?:oklch|rgb|rgba|hsl|hsla)\()/i.test(css.replace(/\/\*[\s\S]*?\*\//g,'')),fontTokens:[...css.matchAll(/font-family:\s*([^;]+);/g)].every(m=>m[1].startsWith('var('))}};
const server=http.createServer((req,res)=>{const item=assets[req.url];if(!item){res.writeHead(404);res.end();return;}res.setHeader('Content-Type',item[1]);res.end(fs.readFileSync(staticDir+item[0]));});
(async()=>{
await act(()=>new Promise(resolve=>server.listen(0,'127.0.0.1',resolve)));
const browser=await act(()=>chromium.launch({channel:'msedge',headless:true}));
const ctx=await act(()=>browser.newContext({viewport:{width:1440,height:1000}}));
try {
await act(()=>ctx.route('**/api/chats**',route=>route.fulfill({json:route.request().url().endsWith('/api/chats')?{chats:[fixture],model:fixture.model,busy:false}:{chat:fixture}})));
const p=await act(()=>ctx.newPage());
results.errors=[];p.on('pageerror',e=>results.errors.push(String(e)));
await act(()=>p.goto('http://127.0.0.1:'+server.address().port));
await act(()=>p.waitForFunction(()=>document.querySelector('.message.assistant')));
results.computed=await act(()=>p.evaluate(()=>{
  const canvas=document.createElement('canvas');canvas.width=canvas.height=1;const c=canvas.getContext('2d',{willReadFrequently:true});
  function rgba(color){c.clearRect(0,0,1,1);c.fillStyle=color;c.fillRect(0,0,1,1);return [...c.getImageData(0,0,1,1).data];}
  function hex(color){return '#'+rgba(color).slice(0,3).map(v=>v.toString(16).padStart(2,'0')).join('');}
  function lum(color){return rgba(color).slice(0,3).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
  function ratio(a,b){const l1=lum(a),l2=lum(b);return (Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);}
  function effectiveBg(el){for(let n=el;n;n=n.parentElement){const bg=getComputedStyle(n).backgroundColor;if(rgba(bg)[3]===255)return bg;}return getComputedStyle(document.body).backgroundColor;}
  const cs=getComputedStyle(document.documentElement);const names=[...cs].filter(n=>n.startsWith('--color-'));
  const colors=Object.fromEntries(names.map(n=>[n,hex(cs.getPropertyValue(n))]));
  const pairs=[];
  for(const el of document.querySelectorAll('body *')) {
    if(!el.getClientRects().length || el.closest('dialog:not([open])') || getComputedStyle(el).visibility==='hidden' || el.disabled) continue;
    const text=[...el.childNodes].some(n=>n.nodeType===Node.TEXT_NODE&&n.textContent.trim());
    const icon=el.tagName.toLowerCase()==='svg';if(!text&&!icon)continue;
    const s=getComputedStyle(el), bg=effectiveBg(el), threshold=icon||parseFloat(s.fontSize)>=24||(parseFloat(s.fontSize)>=18&&Number(s.fontWeight)>=700)?3:4.5;
    pairs.push({element:el.id||el.className.baseVal||el.className||el.tagName,fg:hex(s.color),bg:hex(bg),ratio:+ratio(s.color,bg).toFixed(3),threshold});
  }
  const content=document.querySelector('.message.assistant .message-content'),s=getComputedStyle(content);c.font=s.font;
  const width=content.getBoundingClientRect().width, ch=c.measureText('0').width;
  return {root:getComputedStyle(document.documentElement).backgroundColor,body:hex(getComputedStyle(document.body).backgroundColor),workspace:hex(getComputedStyle(document.querySelector('#workspace')).backgroundColor),colors,pairs,failures:pairs.filter(p=>p.ratio<p.threshold),measure:{width,ch,characters:width/ch,font:s.font},buttons:[...document.querySelectorAll('button')].filter(e=>e.getClientRects().length&&!e.closest('dialog:not([open])')).map(e=>({id:e.id||e.className,lineHeight:getComputedStyle(e).lineHeight,fontSize:getComputedStyle(e).fontSize,alignItems:getComputedStyle(e).alignItems,height:e.getBoundingClientRect().height})),tokenRatios:{mutedOnSoft:ratio(cs.getPropertyValue('--color-muted'),cs.getPropertyValue('--color-soft')),inkOnPaper:ratio(cs.getPropertyValue('--color-ink'),cs.getPropertyValue('--color-paper')),accentInk:ratio(cs.getPropertyValue('--color-accent-ink'),cs.getPropertyValue('--color-accent')),hoverAccent:ratio(cs.getPropertyValue('--color-accent-ink'),cs.getPropertyValue('--color-accent-hover')),pressedAccent:ratio(cs.getPropertyValue('--color-accent-ink'),cs.getPropertyValue('--color-accent-pressed')),fieldBorder:ratio(cs.getPropertyValue('--color-field-rule'),cs.getPropertyValue('--color-surface'))}};
}));
const field=()=>p.locator('#message').evaluate(e=>{const s=getComputedStyle(e);return{outlineWidth:s.outlineWidth,outlineColor:s.outlineColor,outlineOffset:s.outlineOffset,borderWidth:s.borderWidth};});
await act(()=>p.locator('#sync').focus());results.fieldRest=await act(field);
await act(()=>p.locator('#message').focus());results.fieldFocus=await act(field);
const selector=p.locator('.chat-select');const rect=await act(()=>selector.boundingBox());
await act(()=>p.mouse.move(rect.x+rect.width/2,rect.y+rect.height/2));
results.hover=await act(()=>selector.evaluate(e=>({background:getComputedStyle(e).backgroundColor,transform:getComputedStyle(e).transform})));
await act(()=>p.mouse.down());
await act(()=>p.waitForFunction(()=>getComputedStyle(document.querySelector('.chat-select')).transform!=='none'));
results.pressed=await act(()=>selector.evaluate(e=>({active:e.matches(':active'),background:getComputedStyle(e).backgroundColor,transform:getComputedStyle(e).transform})));
await act(()=>p.mouse.up());
await act(()=>p.locator('[data-action]').click());
results.inputFocus=await act(()=>p.locator('#chat-name').evaluate(e=>{const s=getComputedStyle(e);return{outlineWidth:s.outlineWidth,outlineColor:s.outlineColor,outlineOffset:s.outlineOffset,borderWidth:s.borderWidth};}));
await act(()=>p.locator('#cancel-manage').click());
await act(()=>p.screenshot({path:root+'swarm-report/goost-step10-typography.png',fullPage:true}));
assert(results.computed.measure.characters<=75);
assert(results.computed.buttons.every(b=>parseFloat(b.lineHeight)===parseFloat(b.fontSize)));
assert.equal(results.computed.body,'#161c29');
assert.equal(results.computed.workspace,'#161c29');
assert.equal(results.computed.colors['--color-accent'],'#fcbf40');
assert.deepEqual(results.computed.failures,[]);
assert.deepEqual(results.errors,[]);
assert(Object.values(results.source).every(Boolean));
delete results.computed.pairs;
console.log(JSON.stringify(results,null,2));
} finally {await act(()=>ctx.close());await act(()=>browser.close());await act(()=>new Promise(resolve=>server.close(resolve)));}
})().catch(e=>{console.error(e);process.exitCode=1;server.close();});
