"""Past-only seed references. Wallet-only input is NOT marked-to-market equity.

No inferred margin allocation; no current/final balance applied to historic orders.
"""
from __future__ import annotations
import bisect
import json
import math
import re
from collections import defaultdict
from .model import time_us,number
from .performance_ledger import PnlStore,finite,same

VERSION='seed-1'
DAY_US=86_400_000_000
MAX_AGE_US=36*3_600_000_000
SCHEMA='''
CREATE TABLE IF NOT EXISTS seed_snapshots (
 source TEXT NOT NULL, row_key TEXT NOT NULL, t INTEGER NOT NULL,
 wallet_btc REAL, equity_btc REAL, account TEXT NOT NULL,
 precision TEXT NOT NULL, quality TEXT NOT NULL,
 PRIMARY KEY(source,row_key));
CREATE INDEX IF NOT EXISTS seed_time ON seed_snapshots(t);
CREATE TABLE IF NOT EXISTS seed_blocks (
 source TEXT NOT NULL, day INTEGER NOT NULL, account TEXT NOT NULL, reason TEXT NOT NULL,
 PRIMARY KEY(source,day,account));
CREATE TABLE IF NOT EXISTS seed_imports (
 digest TEXT NOT NULL, parser TEXT NOT NULL, report TEXT NOT NULL,
 PRIMARY KEY(digest,parser));
'''
def norm(key):return re.sub(r'[\s_\-()\[\]]','',str(key).lstrip('\ufeff')).lower()
def normalized(row):return {norm(k):v for k,v in row.items() if k is not None}
def field(row,*keys):
    for key in keys:
        v=row.get(norm(key))
        if v is not None and str(v).strip().lower() not in {'','nan','none','null'}:return str(v).strip()
    return None

def recognizes(headers):
    return bool({norm(x) for x in headers} & {'walletbalance','walletbalancebtc','walletbtc','equitybtc','equityestimatebtc','marginbalancebtc','지갑잔고btc','순자산btc'})

def parse_stamp(text):
    text=str(text).strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}D',text):text=text[:-1]
    date_only=bool(re.fullmatch(r'\d{4}[-/]\d{2}[-/]\d{2}',text))
    text=text.replace('/','-')
    if len(text)>10 and text[10]=='D':text=text[:10]+'T'+text[11:]
    return time_us(text),'date_only' if date_only else 'timestamp'

def parse_snapshot(raw):
    r=normalized(raw);status=(field(r,'transactstatus','status') or '').lower()
    if status in {'canceled','cancelled','rejected','pending','unconfirmed','failed','new'}:return None
    if status and status not in {'completed','complete','confirmed','success','succeeded','done'}:raise ValueError('확인되지 않은 잔고 거래 상태: '+status)
    stamp=field(r,'timestamp','asofutc','asof','transacttime','datetime','time','date','시각','날짜')
    if not stamp:raise ValueError('잔고 시각 열 미확인')
    t,precision=parse_stamp(stamp);account=field(r,'account','accountid','accountkey') or 'default'
    kind=(field(r,'transacttype','type') or '').lower()
    wallet=field(r,'walletbalancebtc','walletbtc','지갑잔고btc')
    equity=field(r,'equitybtc','marginbalancebtc','순자산btc','equityestimatebtc')
    quality='provided_equity_estimate' if field(r,'equityestimatebtc') else 'provided_snapshot'
    if wallet is not None:wallet=number(wallet)
    if equity is not None:equity=number(equity)
    if wallet is None and field(r,'walletbalance') is not None:
        currency=field(r,'currency');unit=(field(r,'unit','balanceunit') or '').lower()
        if currency=='XBt' or unit in {'xbt_satoshi','satoshi','sat','sats'}:scale=100_000_000
        elif currency in {'BTC','XBT'} or unit in {'btc','bitcoin'}:scale=1
        else:raise ValueError('walletBalance 단위 미확인: currency=XBt(사토시) / BTC 또는 wallet_balance_btc 필요')
        wallet=number(field(r,'walletbalance'))/scale
    if wallet is None and equity is None:
        if precision=='date_only' and kind in {'deposit','withdrawal','transfer'}:return {'block':t//DAY_US,'account':account,'reason':'입출금 시각이 날짜까지만 있음'}
        return None
    if precision=='date_only':return {'block':t//DAY_US,'account':account,'reason':'날짜만 있는 잔고/입출금: 장중 선후관계 미확인'}
    key=field(r,'transactid','snapshotid','id') or '|'.join(map(str,(t,wallet,equity,account)))
    return {'t':t,'wallet_btc':wallet,'equity_btc':equity,'account':account,'precision':precision,'quality':quality,'row_key':key}

class SeedBook:
    def __init__(self,rows=(),blocks=()):
        self.rows=[dict(r) for r in rows];self.blocks=[dict(b) for b in blocks]
        self.accounts={r['account'] for r in self.rows}|{b['account'] for b in self.blocks}
        self.by_kind={};self.times={}
        for kind in ('equity','wallet'):
            grouped=defaultdict(list)
            for r in self.rows:
                if r.get(kind+'_btc') is not None:grouped[r['t']].append(r)
            result=[]
            for t,rr in sorted(grouped.items()):
                values=[r[kind+'_btc'] for r in rr];conflict=not all(same(values[0],v) for v in values)
                result.append({'time_us':t,'btc':None if conflict else values[0],'conflict':conflict,'sources':sorted({r['source'] for r in rr}),'source_quality':sorted({r['quality'] for r in rr})})
            self.by_kind[kind]=result;self.times[kind]=[r['time_us'] for r in result]
    def at(self,t,kind=None):
        result={'btc':None,'kind':kind,'time_us':None,'age_seconds':None,'quality':'unavailable','reason':'잔고 자료를 연결하세요.','sources':[]}
        if len(self.accounts)>1:
            result['reason']='서로 다른 계좌의 잔고가 섞여 있습니다. 합산하거나 임의 계좌를 선택하지 않습니다.';return result
        for k in ((kind,) if kind else ('equity','wallet')):
            i=bisect.bisect_left(self.times[k],t)-1
            if i<0:continue
            s=self.by_kind[k][i];result.update(s,kind=k,age_seconds=(t-s['time_us'])/1e6)
            if s['conflict']:
                result.update(btc=None,reason='동일 시각 잔고값 충돌. 이전 잔고로 우회하지 않습니다.');return result
            if t-s['time_us']>MAX_AGE_US:
                result.update(btc=None,reason='직전 잔고가 36시간보다 오래되어 주문 시드 계산을 보류합니다.');return result
            if any(b['day']<=t//DAY_US and (b['day']+1)*DAY_US>s['time_us'] for b in self.blocks):
                result.update(btc=None,reason='시각 불명 잔고/입출금 이후 확정 시각 잔고가 아직 없습니다.');return result
            if not finite(s['btc']) or s['btc']<=0:
                result.update(btc=None,reason='양수 시드가 확인되지 않습니다.');return result
            result.update(quality='historical_reference',reason=('명시적 순자산 관측값을 주문 직전까지 유지한 참고값' if k=='equity' else '지갑잔고 관측값 기준 참고. 미실현손익 제외; 순자산/투입 증거금이 아님'))
            return result
        if self.rows:result['reason']='주문보다 앞선 같은 기준의 잔고가 없습니다. 미래 잔고를 사용하지 않습니다.'
        return result

def order_value(e):
    v=e.get('contract_value_btc')
    if finite(v) and v>0:return v,'provided_contract_value'
    if e.get('symbol')!='XBTUSD':return None,'contract_formula_unverified'
    q=e.get('qty')
    if not finite(q) or q<=0:return None,'quantity_missing'
    for k,quality in (('inverse_price','inverse_vwap'),('avg_price','arithmetic_vwap_estimate'),('first_price','first_fill_price_estimate')):
        price=e.get(k)
        if finite(price) and price>0:return q/price,quality
    return None,'execution_price_missing'

def ratio(value,seed):
    if finite(value) and seed and finite(seed.get('btc')) and seed['btc']>0:
        v=100*value/seed['btc']
        return v if math.isfinite(v) else None
    return None

def order_sizing(e,initial,book):
    current=book.at(e['first_us'],initial.get('kind'));amount,quality=order_value(e)
    before=e.get('position_before');after=e.get('position_after')
    delta=e.get('qty',0)*(1 if e.get('role')=='Entry' else -1)
    isolated=finite(before) and finite(after) and same(before+delta,after)
    pb=e.get('first_price');pa=e.get('last_price')
    if not pa and e.get('last_observed') and e['first_us']==e['last_us']:pa=pb
    vb=before/pb if e.get('symbol')=='XBTUSD' and finite(before) and before>=0 and finite(pb) and pb>0 else None
    va=after/pa if e.get('symbol')=='XBTUSD' and e.get('last_observed') and finite(after) and after>=0 and finite(pa) and pa>0 else None
    if e.get('last_observed') and after==0:va=0.0
    end_seed=book.at(e['last_us'],initial.get('kind'))
    return {'initial_seed':initial,'order_seed':current,'end_seed':end_seed,'order_value_btc':amount,'value_quality':quality,
            'order_initial_seed_pct':ratio(amount,initial),'order_current_seed_pct':ratio(amount,current),
            'before_initial_seed_pct':ratio(vb,initial),'before_current_seed_pct':ratio(vb,current),
            'after_initial_seed_pct':ratio(va,initial),'after_current_seed_pct':ratio(va,end_seed),
            'reduced_position_pct':100*e['qty']/before if e['role']=='Exit' and isolated and before>0 else None,
            'endpoints_isolated':isolated,'after_time_us':e['last_us'],
            'note':'계약 규모/시드 비율. 실제 증거금 투입비율이 아님. 주문가치는 전체 체결 사후 합계/근사; 보유비중은 각 끝점 시각 가격. 다른 체결이 섞인 끝점은 단독 주문 효과로 해석 금지.'}

class SeedStore(PnlStore):
    def __init__(self,directory):
        super().__init__(directory)
        with self.connect() as db:db.executescript(SCHEMA)
        self._seed_book=None
    def invalidate_seed(self):self._seed_book=None
    def seed_book(self):
        if self._seed_book is None:
            with self.connect() as db:
                rows=db.execute('SELECT * FROM seed_snapshots').fetchall();blocks=db.execute('SELECT * FROM seed_blocks').fetchall()
            self._seed_book=SeedBook(rows,blocks)
        return self._seed_book
    def initial_seed(self,events):
        entries=[e for e in events if e.get('role')=='Entry']
        if not entries:return {'btc':None,'kind':None,'reason':'최초 진입 미확인','sources':[]}
        first=min(entries,key=lambda e:e['first_us'])
        if not first.get('first_observed') or first.get('position_before') not in (None,0):
            return {'btc':None,'kind':None,'reason':'관측 최초 주문 이전 보유량 존재/첫 끝점 미확인. 최초 시드로 단정하지 않음','sources':[]}
        s=self.seed_book().at(first['first_us']);s['anchor_us']=first['first_us']
        s['anchor_status']='first_observed_entry' if first.get('position_before') is None else 'flat_to_position'
        return s
    def events(self,episode):
        rows=super().events(episode);initial=self.initial_seed(rows);book=self.seed_book()
        for e in rows:e['sizing']=order_sizing(e,initial,book)
        return rows
    def performance(self,episode):
        p=super().performance(episode);events=self.events(episode);s=self.initial_seed(events)
        p['seed_initial']=s
        p['seed_return_pct']=ratio(p.get('net_pnl_btc'),s) if p.get('position_closed') and not p.get('pnl_conflict') else None
        p['seed_return_note']='해당 포지션 순손익 / 최초 관측 진입 직전 시드 참고값. 동시 포지션·입출금을 합친 계좌 전체 수익률 또는 증거금 ROI가 아닙니다.'
        entries=[e for e in events if e['role']=='Entry'];vals=[e['sizing']['after_initial_seed_pct'] for e in events if finite(e['sizing']['after_initial_seed_pct'])]
        p['seed_first_order_pct']=entries[0]['sizing']['order_initial_seed_pct'] if entries else None
        p['seed_peak_observed_pct']=max(vals) if vals else None
        p['seed_peak_note']='확보된 마지막 체결가격·보유량 끝점 중 최대; 전체 보유구간의 정확한 최대가 아님'
        return p
    def episodes(self,*args,**kwargs):
        rows=super().episodes(*args,**kwargs)
        # Same first-entry boundary checks as the detail panel. No N+1 queries.
        with self.connect() as db:
            first={}
            for r in db.execute("SELECT episode,payload FROM orders WHERE json_extract(payload,'$.role')='Entry' ORDER BY t,id"):
                if r['episode'] not in first:first[r['episode']]=json.loads(r['payload'])
            declared={r['episode'] for r in db.execute("SELECT episode FROM performance_sources WHERE json_extract(payload,'$.end_us') IS NOT NULL AND json_extract(payload,'$.entry_qty')=json_extract(payload,'$.exit_qty')")}
        for r in rows:
            e=first.get(r['id']);s=self.initial_seed([e]) if e else None
            r['seed_return_pct']=ratio(r.get('pnl_btc'),s) if r.get('closed') or r['id'] in declared else None
            r['seed_kind']=s.get('kind') if s else None
        return rows
    def status(self):
        s=super().status()
        with self.connect() as db:
            s['seed_snapshots']=db.execute('SELECT COUNT(*) FROM seed_snapshots').fetchone()[0]
            s['seed_ambiguous_days']=db.execute('SELECT COUNT(DISTINCT day) FROM seed_blocks').fetchone()[0]
        return s
