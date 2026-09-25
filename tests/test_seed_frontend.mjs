import test from 'node:test';import assert from 'node:assert/strict';
import {seedLabel,seedReturnText,seedBasis} from '../web/seed-ui.mjs';
const e={first_us:1e6,last_us:3e6,last_observed:true,sizing:{order_initial_seed_pct:20,order_current_seed_pct:25}};
test('seed labels have explicit contract basis and no pre-completion size leakage',()=>{assert.equal(seedLabel(e,1),'');assert.equal(seedLabel(e,2),'');assert.equal(seedLabel(e,3),'');assert.match(seedLabel(e,4),/20.00%/);assert.match(seedLabel(e,null,'current'),/25.00%/);});
test('wallet is not equity and a zero return is valid',()=>{assert.match(seedBasis({kind:'wallet'}),/미실현손익 제외/);assert.match(seedReturnText({seed_return_pct:0}),/0.000%/);assert.match(seedReturnText({seed_return_pct:-2}),/-2.000%/);});
