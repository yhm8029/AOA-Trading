import test from 'node:test';import assert from 'node:assert/strict';
import {outcomeAvailable,returnText,finalResultMarker} from '../web/pnl-ui.mjs';
test('final result appears only after recorded last fill',()=>{const p={position_closed:true,closed_at_us:1609502400000000,net_pnl_btc:1,net_return_pct:5};assert.equal(outcomeAvailable(p,1609502400),false);assert.equal(outcomeAvailable(p,1609502401),true);assert.equal(outcomeAvailable(p,null),true);});
test('zero is not missing and estimate is explicit',()=>{assert.match(returnText({net_return_pct:0}),/0\.000/);assert.match(returnText({net_return_estimate_pct:5}),/≈/);});
test('no marker invented for missing close bar',()=>{assert.equal(finalResultMarker({position_closed:true,closed_at_us:1609502400000000,net_pnl_btc:1,net_return_pct:5},[{time:1609502400}],'1m',null),null);});
