import test from 'node:test';
import assert from 'node:assert/strict';
import {bucket,groupMarkers,category,label,priceReturn,safeCsv,desiredRange,formatTime} from '../web/core.mjs';
const t=Date.parse('2021-06-04T01:02:30Z')*1000;
const e={id:'SYNTHETIC',time_us:t,event:'ADD_SHORT',direction:'Short',qty:1000000,first_price:101,basis_before:100};
const filters={minQty:0,categories:new Set(['ADD','TP','ENTRY']),showQty:true};
test('timestamps map to UTC containing bar, not nearest bar',()=>{
 assert.equal(bucket(t,1),Date.parse('2021-06-04T01:02:00Z')/1000);
 assert.equal(bucket(t,5),Date.parse('2021-06-04T01:00:00Z')/1000);
 assert.equal(bucket(t,60),Date.parse('2021-06-04T01:00:00Z')/1000);
});
test('short entry above, profit below',()=>{
 const bars=[{time:bucket(t,5),open:100,high:102,low:99,close:101}];
 const out=groupMarkers([e,{...e,id:'TP',event:'TAKE_PROFIT_SHORT'}],bars,5,filters);
 assert.equal(out.groups.length,2);
 assert.equal(out.groups.find(x=>x.events[0].id==='SYNTHETIC').marker.position,'aboveBar');
 assert.equal(out.groups.find(x=>x.events[0].id==='TP').marker.position,'belowBar');
});
test('same-candle markers grouped with constituent events retained',()=>{
 const bars=[{time:bucket(t,5),open:100}];
 const out=groupMarkers([e,{...e,id:'B',time_us:t+1000000}],bars,5,filters);
 assert.equal(out.groups.length,1);assert.equal(out.groups[0].events.length,2);
 assert.match(out.groups[0].marker.text,/×2/);
});
test('missing candles never snap event to another timestamp',()=>{
 const out=groupMarkers([e],[{time:bucket(t,5)},{time:bucket(t,5)+300,open:100}],5,filters);
 assert.equal(out.groups.length,0);assert.equal(out.missing,1);
});
test('quantity filter',()=>{
 assert.equal(groupMarkers([e],[{time:bucket(t,5),open:100}],5,{...filters,minQty:2000000}).groups.length,0);
});
test('price deviation is directional, not leveraged return',()=>{
 assert.ok(Math.abs(priceReturn(e)+1)<1e-9);
 assert.ok(Math.abs(priceReturn({...e,direction:'Long'})-1)<1e-9);
 assert.equal(priceReturn({...e,basis_before:null}),null);
});
test('classification labels preserve uncertainty',()=>{
 assert.equal(category({...e,event:'TACTICAL_CUT_SHORT'}),'CUT');
 assert.match(label({...e,event:'TACTICAL_CUT_SHORT'}),/\?/);
 assert.match(label({...e,event:'NEAR_CLOSE_SHORT'}),/대부분/);
});
test('timezone display does not change timestamps',()=>{
 assert.match(formatTime(t,'UTC'),/01:02:30/);
 assert.match(formatTime(t,'Asia/Seoul'),/10:02:30/);
});
test('long episodes are windowed instead of silently downsampling',()=>{
 const range=desiredRange({start_us:t,end_us:t+60*86400*1e6},1);
 assert.equal(range.windowed,true);assert.ok(range.end-range.start<10000*60);
});
test('CSV escaping prevents formula execution',()=>{
 assert.equal(safeCsv('=HYPERLINK("evil")'),'"\'=HYPERLINK(""evil"")"');
 assert.equal(safeCsv('ordinary'),'"ordinary"');
});
