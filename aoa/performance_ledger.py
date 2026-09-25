"""Position-level reported net PNL and explicitly denominated returns.

Never use Binance prices, invented leverage or endpoint interpolation for PNL.
Reported totals and their source identities are retained separately from orders.
"""
from __future__ import annotations
import json
import math
from collections import defaultdict
from .model import number, pick, time_us, present_order
from .study import StudyStore
from .review import performance as reference_performance

LEDGER_SCHEMA = '''
CREATE TABLE IF NOT EXISTS performance_sources (
 episode TEXT NOT NULL, source TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(episode,source));
CREATE TABLE IF NOT EXISTS performance_imports (
 digest TEXT NOT NULL, parser_version TEXT NOT NULL, report TEXT NOT NULL,
 PRIMARY KEY(digest,parser_version));
'''
PARSER_VERSION = 'net-return-1'
ALIASES = {
 'episode': ('episode_id','ep_id','ID','포지션ID','id'),
 'symbol': ('symbol','contract','계약'),
 'direction': ('direction','방향'),
 'net_pnl_btc': ('net_pnl_btc','episode_net_pnl_btc','pnl_btc','net_btc','최종 순손익(BTC)'),
 'gross_pnl_btc': ('gross_pnl_btc','price_pnl_btc','gross_btc','가격손익(BTC)'),
 'trade_fee_btc': ('trade_fee_btc','trading_fee_btc','fees_btc','fee_btc','거래수수료(BTC)'),
 'funding_fee_btc': ('funding_fee_btc','funding_btc','펀딩비(BTC)'),
 'entry_qty': ('entry_qty','qty_entry','entry_quantity','cum_entry_qty','누적 진입수량'),
 'exit_qty': ('exit_qty','qty_exit','exit_quantity','cum_exit_qty','누적 청산수량'),
 'entry_value_btc': ('entry_value_btc','entry_notional_btc','cumulative_entry_value_btc','누적 진입계약가치(BTC)'),
 'start': ('start','entry_time','first_entry','start_time','최초 진입시각'),
 'end': ('end','exit_time','last_exit','end_time','최종 청산시각'),
}

def finite(x):
    return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def same(a,b):
    if finite(a) and finite(b):
        return math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-7)
    return a == b

def tidy(row):
    return {str(k).strip().lstrip('\ufeff'):v for k,v in row.items()}

def is_summary(headers):
    h=set(headers)
    return bool(h.intersection(ALIASES['episode'])) and bool(h.intersection(ALIASES['symbol'])) and bool(h.intersection(ALIASES['net_pnl_btc'])) and not h.intersection({'orderid','source_orderid','order_id','주문ID'})

def summary_row(row):
    row=tidy(row)
    r={k:pick(row,*names) for k,names in ALIASES.items()}
    if r['episode'] is None or not r['symbol'] or r['net_pnl_btc'] is None:
        raise ValueError('손익표의 ID·계약·최종 순손익(BTC)이 필요합니다.')
    r['episode']=str(r['episode']).removesuffix('.0')
    r['symbol']=str(r['symbol']).upper()
    d=str(r['direction'] or '').lower()
    r['direction']={'long':'Long','롱':'Long','short':'Short','숏':'Short'}.get(d)
    for k in ('net_pnl_btc','gross_pnl_btc','trade_fee_btc','funding_fee_btc','entry_qty','exit_qty','entry_value_btc'):
        r[k]=number(r[k])
    for k in ('entry_qty','exit_qty','entry_value_btc'):
        if r[k] is not None and r[k]<=0:raise ValueError(k+' must be positive')
    for k in ('start','end'):
        r[k+'_us']=time_us(r.pop(k)) if r[k] is not None else None
    if r['start_us'] is not None and r['end_us'] is not None and r['start_us']>r['end_us']:
        raise ValueError('손익표 종료시각이 시작보다 빠릅니다.')
    if all(finite(r[k]) for k in ('gross_pnl_btc','trade_fee_btc','funding_fee_btc')):
        if not same(r['gross_pnl_btc']-r['trade_fee_btc']-r['funding_fee_btc'],r['net_pnl_btc']):
            raise ValueError('가격손익 - 거래수수료 - 펀딩비 != 최종 순손익: 부호/단위 확인')
    return r

def put_summary(db,row,source):
    r=summary_row(row)
    # No reusing ID alone across contracts; mismatch is checked again when queried.
    db.execute('INSERT OR REPLACE INTO performance_sources VALUES(?,?,?)',
               (r['episode'],source,json.dumps(r,ensure_ascii=False,allow_nan=False)))

def reconcile(sources,events):
    merged={}; conflicts=[]
    for s in sources:
        for k,v in s.items():
            if v is None:continue
            if k in merged and not same(merged[k],v):conflicts.append(k)
            else:merged[k]=v
    for k in ('symbol','direction'):
        values={e.get(k) for e in events if e.get(k)}
        if len(values)>1 or (merged.get(k) and values and merged[k] not in values):conflicts.append(k)
    if events:
        lo=min(e['first_us'] for e in events);hi=max(e['last_us'] for e in events)
        if merged.get('start_us') is not None and lo<merged['start_us']-1_000_000:conflicts.append('start_us')
        if merged.get('end_us') is not None and hi>merged['end_us']+1_000_000:conflicts.append('end_us')
    return merged,sorted(set(conflicts))

def result_metrics(events,sources=(),margin_btc=None):
    p=reference_performance(events,margin_btc)
    p.update(net_return_pct=None,net_return_estimate_pct=None,entry_value_btc=None,
             return_basis='cumulative_entry_contract_value_btc',return_quality='unavailable',
             gross_pnl_btc=None,trade_fee_btc=None,funding_fee_btc=None,
             closed_at_us=None,position_closed=False,ledger_verified=False,
             denominator_entry_orders=0,observed_entry_orders=0,entry_qty_coverage_pct=None,
             reasons=[],sources=[],formula='100 × 最終純損益BTC / 累計進入契約價值BTC',
             net_return_note='누적 진입 계약가치 기준. 재진입을 매번 합산하며 증거금·계좌 수익률이 아닙니다.')
    ledger,conflicts=reconcile(sources,events)
    if conflicts:
        p.update(net_pnl_btc=None,pnl_conflict=True)
        p['reasons'].append('손익자료/주문 연결 충돌: '+', '.join(conflicts));return p
    net_values=[e.get('episode_pnl_btc') for e in events if finite(e.get('episode_pnl_btc'))]
    if ledger.get('net_pnl_btc') is not None:net_values.append(ledger['net_pnl_btc'])
    if net_values and not all(same(net_values[0],v) for v in net_values):
        p.update(net_pnl_btc=None,pnl_conflict=True);p['reasons'].append('출처별 최종 순손익이 서로 다릅니다.');return p
    net=net_values[0] if net_values else None
    p['net_pnl_btc']=net
    for k in ('gross_pnl_btc','trade_fee_btc','funding_fee_btc'):
        p[k]=ledger.get(k)
    entries=[e for e in events if e.get('role')=='Entry' and finite(e.get('qty')) and e['qty']>0]
    exits=[e for e in events if e.get('role')=='Exit' and finite(e.get('qty')) and e['qty']>0]
    eq=sum(e['qty'] for e in entries);xq=sum(e['qty'] for e in exits)
    p['observed_entry_orders']=len(entries)
    p['observed_entry_qty']=eq;p['observed_exit_qty']=xq
    expected=ledger.get('entry_qty');expected_exit=ledger.get('exit_qty')
    p['entry_qty_coverage_pct']=100*eq/expected if expected else None
    declared_closed=ledger.get('end_us') is not None and expected is not None and expected_exit is not None and same(expected,expected_exit)
    last=max(events,key=lambda e:(e['last_us'],e['first_us'])) if events else None
    inferred_closed=bool(entries and exits and same(eq,xq) and any(e.get('position_before')==0 for e in entries)
                         and last.get('role')=='Exit' and last.get('position_after')==0 and last.get('last_observed'))
    p['position_closed']=bool(declared_closed or inferred_closed)
    p['closed_at_us']=ledger.get('end_us') if declared_closed else last['last_us'] if inferred_closed else None
    full=bool(declared_closed and same(eq,expected) and same(xq,expected_exit))
    if (expected is not None and eq>expected+1e-6) or (expected_exit is not None and xq>expected_exit+1e-6):
        p['reasons'].append('주문 수량이 포지션 원장 합계보다 큽니다. 중복/잘못된 연결 확인');return p
    p['ledger_verified']=full
    if net is None:p['reasons'].append('최종 순손익 자료를 연결하세요: 손익 XLSX / episodes.csv / 기존 분석 ZIP')
    if not p['position_closed']:p['reasons'].append('전량 종료시각·완전한 진입/감량 경계 미확인')
    # Denominator can be supplied by a position ledger; never confuse net execution cost with entry turnover.
    den=ledger.get('entry_value_btc')
    exact=bool(den and declared_closed)
    if den is not None and not declared_closed:den=None
    if den is None and entries:
        symbols={e.get('symbol') for e in events if e.get('symbol')}
        if symbols != {'XBTUSD'}:
            p['reasons'].append('이 계약의 BTC 계약가치 산식 미확인. XBTUSD 산식을 다른 계약에 적용하지 않음')
        else:
            vals=[];approx=False
            for e in entries:
                v=e.get('contract_value_btc')
                if finite(v) and v>0:vals.append(v);continue
                inv=e.get('inverse_price')
                if finite(inv) and inv>0:vals.append(e['qty']/inv);continue
                px=e.get('avg_price')
                if finite(px) and px>0:
                    vals.append(e['qty']/px);approx=True
                elif e.get('last_observed') and e['first_us']==e['last_us'] and finite(e.get('first_price')) and e['first_price']>0:
                    vals.append(e['qty']/e['first_price'])
                else:break
            p['denominator_entry_orders']=len(vals)
            # Known incomplete turnover must not receive even an estimated whole-position return.
            incomplete=(expected is not None and not same(eq,expected)) or (expected_exit is not None and not same(xq,expected_exit))
            if len(vals)==len(entries) and not incomplete and p['position_closed']:
                den=math.fsum(vals);exact=full and not approx
            else:
                p['reasons'].append('진입 계약가치/수량 전체성 미확인. 원본 orders.csv/손익표를 함께 연결하세요.')
    p['entry_value_btc']=den
    if den is not None and den>0 and net is not None and p['position_closed']:
        value=100*net/den
        if math.isfinite(value):
            if exact:p.update(net_return_pct=value,return_quality='ledger_and_denominator_verified')
            else:
                p.update(net_return_estimate_pct=value,return_quality='denominator_estimate')
                p['reasons'].append('순손익은 제공값, 분모는 관측 주문 평균가격/전체성 미검증 근사값. 확정 수익률과 구분')
    if net is not None and finite(margin_btc) and margin_btc>0:
        p['reference_roi_pct']=100*net/margin_btc
    p['formula']='최종 순손익(BTC) ÷ 누적 진입 계약가치(BTC) × 100'
    return p

class PnlStore(StudyStore):
    def __init__(self,directory):
        super().__init__(directory)
        with self.connect() as db:db.executescript(LEDGER_SCHEMA)

    def performance(self,episode):
        with self.connect() as db:
            rows=db.execute('SELECT source,payload FROM performance_sources WHERE episode=?',(str(episode),)).fetchall()
            m=db.execute('SELECT btc FROM reference_margins WHERE episode=?',(str(episode),)).fetchone()
        p=result_metrics(self.events(episode),[json.loads(r['payload']) for r in rows],m[0] if m else None)
        p['sources']=[r['source'] for r in rows]
        return p

    def episodes(self,symbol='XBTUSD',year='',direction='',result='',search='',year_mode='entry'):
        rows=super().episodes(symbol,year,direction,'',search,year_mode)
        # Batch once; no thousands of per-position DB connections on every sidebar refresh.
        with self.connect() as db:
            summaries=defaultdict(list)
            for r in db.execute('SELECT episode,payload FROM performance_sources'):summaries[r['episode']].append(json.loads(r['payload']))
            groups=defaultdict(list)
            for r in db.execute('SELECT episode,payload FROM orders ORDER BY t,id'):groups[r['episode']].append(present_order(json.loads(r['payload'])))
        out=[]
        for row in rows:
            p=result_metrics(groups[row['id']],summaries[row['id']])
            row.update(pnl_btc=p['net_pnl_btc'],net_return_pct=p['net_return_pct'],net_return_estimate_pct=p['net_return_estimate_pct'])
            value=p['net_pnl_btc'];row['result']='Unknown' if value is None else 'Win' if value>0 else 'Loss' if value<0 else 'Flat'
            if not result or row['result']==result:out.append(row)
        return out
