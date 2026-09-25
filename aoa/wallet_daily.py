"""Date-only wallet references. NEVER reconstruct a missing hour.

A day-close value is usable only after its whole source date has ended. It is
stored separately from timestamped equity, and remains a historical reference,
not an order-time balance. All examples/tests use artificial balances.
"""
from __future__ import annotations
import bisect
import hashlib
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from .model import time_us, number

DAY_US = 86_400_000_000
MAX_AGE_US = 36 * 3_600_000_000
DAILY_SCHEMA = '''
CREATE TABLE IF NOT EXISTS seed_daily_rows (
 source TEXT NOT NULL, row_key TEXT NOT NULL, day INTEGER NOT NULL,
 wallet_btc REAL NOT NULL, amount_btc REAL NOT NULL, account TEXT NOT NULL,
 kind TEXT NOT NULL, ordinal INTEGER NOT NULL, quality TEXT NOT NULL,
 PRIMARY KEY(source,row_key));
CREATE INDEX IF NOT EXISTS seed_daily_day ON seed_daily_rows(day);
'''
STAMP_KEYS = ('timestamp','asofutc','asof','datetime','time','date','시각','날짜','transacttime')
CASHFLOW = {'deposit','withdrawal','transfer','transferin','transferout'}

def norm(k):
    return re.sub(r'[\s_\-()\[\]]', '', str(k).lstrip('\ufeff')).lower()

def field(r, *keys):
    for k in keys:
        v = r.get(norm(k))
        if v is not None and str(v).strip().lower() not in {'','nan','none','null'}:
            return str(v).strip()
    return None

def parse_stamp(text):
    text = str(text).strip().replace('/', '-')
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}D', text):
        text = text[:-1]
    if not re.match(r'^\d{4}-\d{2}-\d{2}(?:$|[DT ])', text):
        raise ValueError('완전한 날짜가 없는 시간값: 시(hour)를 추정하지 않습니다.')
    if len(text) > 10 and text[10] == 'D':
        text = text[:10] + 'T' + text[11:]
    return time_us(text), 'date_only' if len(text) == 10 else 'timestamp'

def resolve_time(r):
    """A malformed preferred field must not hide a usable date/full timestamp."""
    dates = []
    full = []
    for k in STAMP_KEYS:
        text = field(r, k)
        if text is None:
            continue
        try:
            t, precision = parse_stamp(text)
        except (ValueError, OverflowError):
            continue
        if precision == 'timestamp':
            full.append((t, precision, k))
        else:
            dates.append((t, precision, k))
    # timestamp is the balance observation; transacttime is a different event.
    if full:
        return full[0]
    if dates:
        if len({x[0] for x in dates}) != 1:
            raise ValueError('날짜 열들이 서로 다릅니다. 임의 날짜를 선택하지 않습니다.')
        return dates[0]
    raise ValueError('완전한 잔고 날짜/시각 미확인. 잘린 timestamp를 날짜로 만들지 않습니다.')

def raw_scale(r):
    currency = field(r, 'currency')
    unit = (field(r, 'unit', 'balanceunit') or '').lower()
    if currency == 'XBt' or unit in {'xbt_satoshi','satoshi','sat','sats'}:
        return Decimal(100_000_000)
    if currency in {'BTC','XBT'} or unit in {'btc','bitcoin'}:
        return Decimal(1)
    raise ValueError('walletBalance/amount 단위 미확인: currency=XBt 또는 명시적 BTC 열 필요')

def scaled(text, scale=Decimal(1)):
    if text is None:
        return None
    try:
        value = Decimal(str(text).replace(',', '')) / scale
    except (InvalidOperation, ZeroDivisionError):
        raise ValueError('유효한 잔고/금액 숫자가 아닙니다.') from None
    result = float(value)
    if not value.is_finite() or not math.isfinite(result):
        raise ValueError('유한한 잔고/금액 숫자가 필요합니다.')
    return result

def parse_snapshot(raw):
    r = {norm(k):v for k,v in raw.items() if k is not None}
    status = (field(r, 'transactstatus','status') or '').lower()
    if status in {'canceled','cancelled','rejected','pending','unconfirmed','failed','new'}:
        return None
    if status and status not in {'completed','complete','confirmed','success','succeeded','done'}:
        raise ValueError('확인되지 않은 잔고 거래 상태: ' + status)
    t, precision, selected_field = resolve_time(r)
    account = field(r, 'account','accountid','accountkey') or 'default'
    kind = (field(r, 'transacttype','type') or '').lower()
    wallet = scaled(field(r, 'walletbalancebtc','walletbtc','지갑잔고btc'))
    equity = scaled(field(r, 'equitybtc','marginbalancebtc','순자산btc','equityestimatebtc'))
    if wallet is None and field(r, 'walletbalance') is not None:
        wallet = scaled(field(r, 'walletbalance'), raw_scale(r))
    if wallet is None and equity is None:
        if precision == 'date_only' and kind in CASHFLOW:
            return {'block':t//DAY_US,'account':account,'reason':'입출금 시각이 날짜까지만 있음'}
        return None
    key = field(r, 'transactid','snapshotid','id')
    if precision == 'date_only':
        amount = scaled(field(r, 'amountbtc','cashflowbtc'))
        if amount is None and field(r, 'amount') is not None:
            amount = scaled(field(r, 'amount'), raw_scale(r))
        if wallet is None or amount is None:
            return {'block':t//DAY_US,'account':account,'reason':'날짜만 있는 잔고: 일별 검산용 walletbalance/amount 미확보'}
        if key is None:
            key = hashlib.sha256(repr((t,wallet,amount,account,kind)).encode()).hexdigest()
        row = {'daily':t//DAY_US,'wallet_btc':wallet,'amount_btc':amount,
               'account':account,'kind':kind,'row_key':key,'quality':'date_only_ledger'}
        if kind in CASHFLOW:
            row.update(block=t//DAY_US,reason='입출금 날짜는 있으나 장중 시각이 없습니다.')
        return row
    quality = 'provided_equity_estimate' if field(r, 'equityestimatebtc') else 'provided_snapshot'
    if key is None:
        key = '|'.join(map(str,(t,wallet,equity,account)))
    return {'t':t,'wallet_btc':wallet,'equity_btc':equity,'account':account,
            'precision':precision,'quality':quality,'row_key':key}

def close_enough(a, b):
    # No relative tolerance growing into material BTC discrepancies.
    return math.isclose(a, b, rel_tol=0, abs_tol=1.01e-8)

def daily_close(rows):
    """Validate forward/reverse file order. Do not pick an arbitrary last row."""
    rows = sorted(rows, key=lambda r:r['ordinal'])
    possibilities = []
    for candidate in (rows, list(reversed(rows))):
        start = candidate[0]['wallet_btc'] - candidate[0]['amount_btc']
        if all(close_enough(a['wallet_btc'] + b['amount_btc'], b['wallet_btc'])
               for a,b in zip(candidate,candidate[1:])):
            total = math.fsum(r['amount_btc'] for r in candidate)
            end = candidate[-1]['wallet_btc']
            if close_enough(start + total, end):
                possibilities.append((start,end,total))
    if not possibilities:
        return {'valid':False,'btc':None,'reason':'일별 amount와 walletbalance 연결 불일치'}
    if any(not all(close_enough(a,b) for a,b in zip(possibilities[0],p)) for p in possibilities):
        return {'valid':False,'btc':None,'reason':'일별 순서가 둘 이상 가능하고 마감 잔고가 다릅니다.'}
    start,end,total = possibilities[0]
    return {'valid':True,'btc':end,'opening_btc':start,'amount_btc':total,
            'row_count':len(rows),'reason':'일별 금액·잔고 연결 검산 일치'}

class DailyBook:
    def __init__(self, rows=()):
        self.rows = [dict(r) for r in rows]
        self.accounts = {r['account'] for r in self.rows}
        by_source = defaultdict(list)
        for r in self.rows:
            by_source[(r['source'],r['account'],r['day'])].append(r)
        by_day = defaultdict(list)
        for (source,account,day), rr in by_source.items():
            point = daily_close(rr)
            point.update(source=source,account=account,day=day)
            by_day[day].append(point)
        self.points = []
        for day, pp in sorted(by_day.items()):
            good = all(p['valid'] for p in pp)
            if good:
                good = all(all(close_enough(pp[0][k],p[k]) for k in ('btc','opening_btc','amount_btc')) for p in pp)
            reason = '출처별 일별 잔고 충돌/검산 실패' if not good else '일별 원장 연결 일치'
            self.points.append({'day':day,'btc':pp[0]['btc'] if good else None,
                                'valid':good,'reason':reason,'sources':sorted({p['source'] for p in pp})})
        self.days = [p['day'] for p in self.points]
    def at(self, t, blocks=()):
        result = {'btc':None,'kind':'wallet','time_us':None,'age_seconds':None,
                  'quality':'unavailable','basis':'prior_day_ledger_close','sources':[],
                  'reason':'주문 날짜 이전의 일별 잔고가 없습니다. 당일·미래 잔고를 사용하지 않습니다.'}
        i = bisect.bisect_left(self.days, t//DAY_US) - 1
        if i < 0:
            return result
        p = self.points[i]
        available = (p['day']+1)*DAY_US
        reference_day = (datetime(1970,1,1)+timedelta(days=p['day'])).strftime('%Y-%m-%d')
        result.update(reference_day=reference_day,available_from_us=available,
                      age_seconds=(t-available)/1e6,sources=p['sources'])
        if not p['valid']:
            result['reason'] = p['reason'] + '. 이전 정상 날짜로 우회하지 않습니다.'
            return result
        if any(b['day'] <= t//DAY_US and (b['day']+1)*DAY_US > available for b in blocks):
            result['reason'] = '시각 불명 입출금/거부 잔고가 있어 해당 구간 비중을 보류합니다. 자료 미연결이 아닙니다.'
            return result
        if t-available > MAX_AGE_US:
            result['reason'] = '이전 일별 잔고가 36시간 이상 오래되었습니다. 시드 비중은 보류합니다.'
            return result
        if p['btc'] is None or not math.isfinite(p['btc']) or p['btc'] <= 0:
            result['reason'] = '이전 일별 잔고가 0 이하이거나 유효하지 않습니다.'
            return result
        result.update(btc=p['btc'],quality='daily_ledger_reference',
                      reason=reference_day+' 원장 마감 잔고 기준 참고. 주문 직전 잔고·평가 순자산이 아닙니다. 당일 손익과 미실현손익은 반영하지 않습니다.')
        return result
