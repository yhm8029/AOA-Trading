"""Explicit source adapters. Never turn candle features into fabricated OHLCV."""
from __future__ import annotations
import hashlib
import math
import re
from datetime import datetime, timezone
from typing import Any

TIMEFRAMES = (1, 5, 15, 60, 240, 1440)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
SYMBOL = re.compile(r'^[A-Z0-9_]{2,30}$')


def number(value: Any, *, integer: bool = False, positive: bool = False):
    if value is None or str(value).strip().lower() in ('', 'none', 'nan', 'null'):
        return None
    n = float(value)
    if not math.isfinite(n):
        raise ValueError('Non-finite number')
    if positive and n <= 0:
        raise ValueError('Price must be positive')
    if integer and n != int(n):
        raise ValueError('Expected integer contracts/timestamp')
    return int(n) if integer else n


def pick(row: dict, *keys, default=None):
    for k in keys:
        if row.get(k) is not None and str(row[k]).strip() != '':
            return row[k]
    return default


def time_us(value: Any) -> int:
    text = str(value).strip()
    if re.fullmatch(r'\d+(\.\d+)?', text):
        n = float(text)
        if n >= 1e14:
            result = int(n)
        elif n >= 1e11:
            result = int(n * 1000)
        else:
            result = int(n * 1000000)
    else:
        dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = dt.astimezone(timezone.utc) - EPOCH
        result = (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds
    if not 1262304000000000 <= result < 4102444800000000:
        raise ValueError('Timestamp outside supported 2010-2099 range')
    return result


def utc(t: int | float) -> str:
    return datetime.fromtimestamp(t / 1000000, timezone.utc).isoformat()


def clean_symbol(value: Any) -> str:
    s = str(value or '').strip().upper()
    if not SYMBOL.fullmatch(s):
        raise ValueError('Invalid symbol')
    return s


def normalize_event(row: dict, source: str, line: int):
    """Support exported events and first/last endpoint context CSVs.

    Quantities and VWAP are GROUP totals, not instantaneous fills. An imported
    taxonomy is retained as retrospective evidence, never silently retrained.
    """
    raw_type = str(pick(row, 'event', 'event_type', default='')).upper()
    role = str(pick(row, 'role', 'raw_role', default='')).lower()
    if role not in ('entry', 'exit'):
        role = 'entry' if raw_type.startswith(('ENTRY', 'ADD', 'FLIP', 'INCREASE')) else 'exit'
    ep = str(pick(row, 'episode_id', 'ep_id', default='')).strip()
    if not ep or len(ep) > 80:
        raise ValueError('Missing or invalid episode_id / ep_id')
    symbol = clean_symbol(pick(row, 'symbol', 'contract', default='XBTUSD' if 'bitmex_vwap' in row else ''))
    direction = str(pick(row, 'direction', default='')).capitalize()
    if direction not in ('Long', 'Short'):
        raise ValueError('Missing Long/Short direction; never guessed from price')
    when = pick(row, 'event_time_utc', 'event_time_assumed_utc', 'timestamp')
    t = time_us(when)
    oid = str(pick(row, 'source_orderid', 'orderid', 'order_id', default='')).strip()
    if not oid:
        oid = str(pick(row, 'event_id', default=''))
    if not oid or len(oid) > 200:
        raise ValueError('Missing order/event identity')
    key = hashlib.sha256(f'{symbol}|{ep}|{oid}|{role}'.encode()).hexdigest()[:28]
    qty = number(pick(row, 'qty', 'quantity', 'order_group_qty_audit_only'), integer=True)
    if qty is None or qty < 0:
        raise ValueError('Missing or negative quantity')
    first = number(pick(row, 'bitmex_first_fill', 'execution_price', 'first_price'), positive=True)
    vwap = number(pick(row, 'bitmex_vwap', 'vwap'), positive=True)
    if first is None and vwap is None:
        raise ValueError('Missing execution price')
    before = number(pick(row, 'qty_before', 'position_before'), integer=True)
    after = number(pick(row, 'qty_after', 'position_after'), integer=True)
    if any(x is not None and x < 0 for x in (before, after)):
        raise ValueError('Negative absolute position snapshot')
    basis = number(pick(row, 'avg_basis_before', 'avg_entry_before', 'basis_before'))
    if basis is not None and basis <= 0:
        basis = None
    stop = number(pick(row, 'stop_trigger'))
    if stop is not None and stop <= 0:
        stop = None
    suffix = direction.upper()
    default_label = ('ENTRY_' if before == 0 else 'ADD_' if before is not None else 'INCREASE_') + suffix if role == 'entry' else 'REDUCE_' + suffix
    allowed = ('ENTRY_', 'ADD_', 'INCREASE_', 'TAKE_PROFIT_', 'TP_', 'TACTICAL_CUT_', 'STOP_', 'CLOSE_', 'REDUCE_', 'NEAR_CLOSE_', 'FLIP_TO_')
    label = raw_type if raw_type.startswith(allowed) else default_label
    warnings = ['GROUPED_ORDER_NOT_SINGLE_FILL', 'TIME_ASSUMED_UTC']
    if raw_type:
        warnings.append('IMPORTED_RETROSPECTIVE_CLASSIFICATION')
    if label.startswith('CLOSE_') and after not in (None, 0):
        label = 'NEAR_CLOSE_' + suffix
        warnings.append('NONZERO_RESIDUAL_NOT_FULL_CLOSE')
    if label.startswith('TACTICAL_CUT_'):
        warnings.append('TACTICAL_INTERPRETATION_NOT_PROVEN')
    if before is not None and after is not None:
        delta = qty if role == 'entry' else -qty
        if before + delta != after:
            warnings.append('GROUP_ENDPOINTS_INCLUDE_INTERLEAVED_ORDERS')
    pair = pick(row, 'reference_pair')
    if pair:
        pair = clean_symbol(pair)
    elif symbol == 'XBTUSD':
        pair = 'BTCUSDT'
    else:
        pair = None
        warnings.append('NO_VERIFIED_MARKET_MAPPING')
    end = pick(row, 'last_time', 'event_end_utc')
    end_t = time_us(end) if end else None
    if end_t is not None and end_t < t:
        raise ValueError('Order end precedes start')
    context = {}
    for k, v in row.items():
        if k.startswith('pre_') and v not in (None, ''):
            try:
                context[k] = number(v)
            except ValueError:
                context[k] = str(v)[:200]
    e = dict(id=key, episode_id=ep, symbol=symbol, direction=direction, time_us=t,
             event_time_utc=utc(t), end_time_us=end_t, event=label, raw_event=raw_type or role,
             raw_role=role, qty=qty, first_price=first, group_vwap=vwap, qty_before=before,
             qty_after=after, basis_before=basis, stop_trigger=stop,
             episode_net_pnl_btc=number(pick(row, 'episode_net_pnl_btc')),
             episode_max_qty=number(pick(row, 'episode_max_qty'), integer=True),
             reference_pair=pair, source_orderid=oid,
             classification_reason=str(pick(row, 'classification_reason', default='원본 역할만 표시; 최초/추가 또는 익절/손절 미확정')),
             source=source, source_row=line, context=context, warnings=warnings,
             phase=str(pick(row, 'phase', default='first')).lower())
    if e['phase'] not in ('first', 'last'):
        raise ValueError('Unknown endpoint phase')
    if e['phase'] == 'last':
        e['last_price'] = first
    return e, 100 if raw_type else 50


def candle(row: dict):
    pair = clean_symbol(pick(row, 'reference_pair', 'pair', 'symbol', default='BTCUSDT'))
    minute = pick(row, 'minute_utc')
    if minute is not None:
        t = number(minute, integer=True) * 60
    else:
        t = time_us(pick(row, 'candle_open_utc', 'time', 'open_time', 'timestamp')) // 1000000
    if t % 60:
        raise ValueError('1m candle timestamp is not minute-aligned')
    if not 1262304000 <= t < 4102444800:
        raise ValueError('Candle time outside supported range')
    values = tuple(number(row.get(k), positive=(k != 'volume')) for k in ('open', 'high', 'low', 'close', 'volume'))
    if any(x is None for x in values):
        raise ValueError('Missing OHLCV field')
    o, h, l, c, v = values
    if l > min(o, c) or h < max(o, c) or l > h or v < 0:
        raise ValueError('Invalid OHLCV')
    return (pair, t, *values)
