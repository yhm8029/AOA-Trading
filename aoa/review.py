"""Research statistics and gap planning. No synthetic fills or inferred collateral."""
from __future__ import annotations
import math
import time
from datetime import datetime, timezone
from .store import Store

MAX_FETCH_SECONDS = 180 * 86400


def finite(value):
    return value is not None and isinstance(value, (int, float)) and math.isfinite(value)


def checked_range(pair, start, end, *, historical=False):
    if not isinstance(pair, str) or not pair.isalnum() or not 5 <= len(pair) <= 20 or pair != pair.upper():
        raise ValueError('올바른 공개 시장 거래쌍이 필요합니다.')
    start, end = int(start) // 60 * 60, (int(end) + 59) // 60 * 60
    if not 1_400_000_000 <= start < end <= 4_102_444_800 or end-start > MAX_FETCH_SECONDS:
        raise ValueError('시세 범위는 한 번에 과거 180일 이내로 선택하세요.')
    if historical and end > int(time.time()) // 60 * 60:
        raise ValueError('완성되지 않은 현재/미래 분봉은 다운로드하지 않습니다.')
    return start, end


def missing_plan(store, pair, start, end):
    """Only absent, non-conflicted minutes are fetch candidates; intervals are end-exclusive."""
    start, end = checked_range(pair, start, end)
    with store.connect() as db:
        valid = {r[0] for r in db.execute('SELECT t FROM candles WHERE pair=? AND t>=? AND t<?', (pair,start,end))}
        blocked = {r[0] for r in db.execute('SELECT t FROM conflicts WHERE pair=? AND t>=? AND t<?', (pair,start,end))}
    ranges, run = [], None
    for t in range(start, end, 60):
        absent = t not in valid and t not in blocked
        if absent and run is None:
            run = t
        if not absent and run is not None:
            ranges.append((run,t)); run = None
    if run is not None:
        ranges.append((run,end))
    expected = (end-start)//60
    return {'pair':pair, 'start':start, 'end':end, 'expected_minutes':expected,
            'valid_minutes':len(valid), 'conflict_minutes':len(blocked),
            'missing_minutes':expected-len(valid),
            'fetchable_minutes':sum((b-a)//60 for a,b in ranges), 'ranges':ranges}


def performance(events, margin_btc=None):
    """Descriptive, quantity-weighted reduction reference price change, NOT account ROI.

    A grouped order may span several fills and basis changes. Its arithmetic VWAP
    versus basis_before is only a group reference approximation. Never reconstruct
    inverse-contract PNL from this approximation or multiply by an assumed leverage.
    """
    exits = [e for e in events if e.get('role') == 'Exit' and finite(e.get('qty')) and e['qty'] > 0]
    valid = []
    for e in exits:
        basis = e.get('basis_before')
        px = e.get('avg_price') or e.get('first_price')
        sign = 1 if e.get('direction') == 'Long' else -1 if e.get('direction') == 'Short' else 0
        if sign and finite(basis) and basis > 0 and finite(px) and px > 0:
            valid.append((e['qty'], sign*(px/basis-1)*100))
    total_qty = sum(e['qty'] for e in exits)
    covered_qty = sum(q for q,p in valid)
    pnl_values = [e['episode_pnl_btc'] for e in events if finite(e.get('episode_pnl_btc'))]
    pnl_conflict = bool(pnl_values) and not all(math.isclose(v,pnl_values[0],rel_tol=1e-9,abs_tol=1e-8) for v in pnl_values)
    pnl = pnl_values[0] if pnl_values and not pnl_conflict else None
    margin = margin_btc if finite(margin_btc) and margin_btc > 0 else None
    return {'price_return_pct':sum(q*p for q,p in valid)/covered_qty if covered_qty else None,
            'price_return_kind':'observed_reductions_group_reference_estimate',
            'covered_exit_orders':len(valid), 'observed_exit_orders':len(exits),
            'covered_exit_qty':covered_qty, 'observed_exit_qty':total_qty,
            'coverage_pct':100*covered_qty/total_qty if total_qty else None,
            'net_pnl_btc':pnl, 'pnl_conflict':pnl_conflict,
            'reference_margin_btc':margin,
            'reference_roi_pct':100*pnl/margin if pnl is not None and margin is not None else None,
            'note':'감량별 수량 × 방향환산(그룹 평균가격/당시 평균단가−1)의 가중평균. 제공된 감량 주문만의 근사값이며 수수료·펀딩·레버리지 미반영. 전체 포지션/계좌 수익률로 해석하지 마세요. 증거금 ROI는 사용자가 입력한 참고 분모 기준입니다.'}


class ReviewStore(Store):
    """Backwards-compatible extension of the existing local-data/viewer.sqlite3."""
    def __init__(self, directory):
        super().__init__(directory)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reference_margins (episode TEXT PRIMARY KEY, btc REAL NOT NULL CHECK(btc>0), updated TEXT DEFAULT CURRENT_TIMESTAMP)')

    def episodes(self, symbol='XBTUSD', year='', direction='', result='', search='', year_mode='entry'):
        if year_mode not in ('entry','overlap'):
            raise ValueError('연도 기준은 entry 또는 overlap입니다.')
        rows = super().episodes(symbol,'',direction,result,search)
        if not year:
            return rows
        y = int(year)
        if not 2014 <= y <= 2099:
            raise ValueError('올바른 연도를 선택하세요.')
        lo = int(datetime(y,1,1,tzinfo=timezone.utc).timestamp())
        hi = int(datetime(y+1,1,1,tzinfo=timezone.utc).timestamp())
        out = []
        for row in rows:
            # Entry year is the first observed order, not final maximum-exposure time.
            match = lo <= row['start'] < hi if year_mode == 'entry' else row['start'] < hi and row['end'] >= lo
            if match:
                row['carried'] = row['start'] < lo
                row['year_floor'] = lo
                row['focus'] = max(lo, row['focus'])
                out.append(row)
        return out

    def candles(self, pair, timeframe, start, end):
        checked_range(pair,start,end)
        data = super().candles(pair,timeframe,start,end)
        plan = missing_plan(self,pair,data['start'],data['end'])
        data['coverage'] = {k:v for k,v in plan.items() if k != 'ranges'}
        data['coverage']['missing_intervals'] = plan['ranges'][:100]
        data['coverage']['interval_count'] = len(plan['ranges'])
        return data

    def performance(self, episode):
        with self.connect() as db:
            row = db.execute('SELECT btc FROM reference_margins WHERE episode=?',(str(episode),)).fetchone()
        return performance(self.events(episode), row[0] if row else None)

    def set_reference_margin(self, episode, value):
        if value in (None,''):
            with self.connect() as db:
                db.execute('DELETE FROM reference_margins WHERE episode=?',(str(episode),))
            return
        amount = float(value)
        if not math.isfinite(amount) or not 0 < amount <= 21_000_000:
            raise ValueError('참고 증거금은 0보다 큰 유한한 BTC 값이어야 합니다.')
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM orders WHERE episode=?',(str(episode),)).fetchone():
                raise ValueError('없는 포지션입니다.')
            db.execute('INSERT INTO reference_margins(episode,btc) VALUES(?,?) ON CONFLICT(episode) DO UPDATE SET btc=excluded.btc,updated=CURRENT_TIMESTAMP',(str(episode),amount))
