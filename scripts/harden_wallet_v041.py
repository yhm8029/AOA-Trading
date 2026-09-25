"""One-off checked hardening before CI; excluded from final release."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
p=ROOT/'aoa/wallet_daily.py';s=p.read_text(encoding='utf-8')
old="row.update(block=t//DAY_US,reason='입출금 날짜는 있으나 장중 시각이 없습니다.')"
new="row.update(block=t//DAY_US,reason='DAILY_RECONCILED_CASHFLOW: 입출금 날짜는 있으나 장중 시각이 없습니다.')"
if old in s:s=s.replace(old,new)
old="        if not p['valid']:\n"
new="        if any(b['day']==p['day'] and not b.get('reason','').startswith('DAILY_RECONCILED_CASHFLOW:') for b in blocks):\n            result['reason']='해당 날짜에 검산에서 제외된 잔고 행이 있습니다. 일부 정상 행만으로 마감 잔고를 확정하지 않습니다.'\n            return result\n        if not p['valid']:\n"
if new not in s:
    assert old in s;s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
p=ROOT/'scripts/integrate_wallet_v041.py';s=p.read_text(encoding='utf-8')
s=s.replace('if old not in s and new in s:return','if new in s:return')
p.write_text(s,encoding='utf-8')
import runpy
runpy.run_path(str(p),run_name='__main__')
p=ROOT/'web/index.html';s=p.read_text(encoding='utf-8');p.write_text(s.replace('v=040','v=041'),encoding='utf-8')
print('WALLET_BLOCKS_HARDENED')
