'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
function harness(){
  const nodes=new Map(), posts=[];
  function node(){return {value:'',children:[],handlers:{},textContent:'',hidden:false,
    append(...items){this.children.push(...items)},replaceChildren(...items){this.children=items},
    addEventListener(type,fn){this.handlers[type]=fn},reset(){},focus(){}};}
  const el=id=>{if(typeof id!=='string') throw Error('ID required');if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
  const ctx=vm.createContext({el,document:{createElement:node},text:(tag,value)=>Object.assign(node(),{textContent:value}),
    crypto:{randomUUID:()=> '11111111-1111-1111-1111-111111111111'},
    taskPost:async(url,payload)=>posts.push({url,payload}),load:async()=>{},generation:1,
    cairoDate:seconds=>String(seconds),window:{confirm:()=>true}});
  const root=path.join(__dirname,'../src/okal_core/static');
  const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
  for(const [begin,end] of [['function taskDueIso(', 'function reminderChoice('],['function dateInputValue(', 'async function taskPost(']])
    vm.runInContext(app.slice(app.indexOf(begin),app.indexOf(end)),ctx);
  vm.runInContext(fs.readFileSync(path.join(root,'local-calendar-ui.js'),'utf8'),ctx);
  return {ctx,el,posts};
}
test('appointment submission serializes real input values and preserves revision on edit',async()=>{
  const {ctx,el,posts}=harness();
  ctx.editLocalCommitment({id:'a'.repeat(32),kind:'event',revision:4,title:'Fixture',notes:'',start_ts:1793754000,end_ts:1793757600,target_date:null,reminder_minutes:15});
  assert.match(el('local-start').value,/^\d{4}-\d\d-\d\dT\d\d:\d\d$/);
  await el('local-calendar-form').handlers.submit({preventDefault(){}});
  assert.equal(posts[0].payload.revision,4);
  assert.equal(Date.parse(posts[0].payload.start)/1000,1793754000);
});
test('goal creation submits date only and reset clears private details',async()=>{
  const {ctx,el,posts}=harness();
  el('local-kind').value='goal';el('local-title').value='Fixture';el('local-target').value='2026-11-10';
  await el('local-calendar-form').handlers.submit({preventDefault(){}});
  assert.equal(posts[0].payload.start,null);assert.equal(posts[0].payload.reminder_minutes,null);
  assert.equal(posts[0].payload.target_date,'2026-11-10');
  el('morning-details').append({textContent:'Private fixture'});
  ctx.resetLocalCalendarView();assert.equal(el('morning-details').children.length,0);
});
test('untrusted titles are rendered as text; late responses do not refill hidden data',async()=>{
  const {ctx,el}=harness();
  ctx.fetch=async()=>({ok:true,json:async()=>({items:[{id:'a'.repeat(32),revision:1,kind:'goal',title:'<img onerror=evil()>',notes:'fixture',target_date:null}]})});
  await ctx.loadLocalCalendar({},0);assert.equal(el('local-calendar-items').children.length,0);
  await ctx.loadLocalCalendar({},1);
  assert.equal(el('local-calendar-items').children[0].children[0].textContent,'هدف · <img onerror=evil()>');
});
