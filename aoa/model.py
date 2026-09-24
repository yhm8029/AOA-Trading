"""Strict data adapters. Never turn group endpoints into a synthetic fill ledger."""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone, timedelta

UTC = timezone.utc
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
TIMEFRAMES = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


def number(value, default=None):
    if value is None or str(value).strip().lower() in {"", "nan", "none", "null"}:
        return default
    n = float(str(value).replace(",", ""))
    if not math.isfinite(n):
        raise ValueError("non-finite number")
    return n


def pick(row, *keys):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def time_us(value):
    """Keep microseconds; naive source times are provisionally UTC, not verified UTC."""
    if value is None:
        raise ValueError("missing timestamp")
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("ISO timestamp required: " + text[:40]) from None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = dt.astimezone(UTC) - EPOCH
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def iso(us):
    return (EPOCH + timedelta(microseconds=us)).isoformat()


def key_for(episode, role, order_id):
    return hashlib.sha256(f"{episode}|{role}|{order_id}".encode()).hexdigest()[:28]


def role_of(value):
    text = str(value or "").upper()
    if text in {"ENTRY", "진입/추가"} or text.startswith(("ENTRY_", "ADD_", "FLIP_")):
        return "Entry"
    if text in {"EXIT", "감소/종료"} or text.startswith(("TAKE_PROFIT", "TP_", "TACTICAL_CUT", "CUT_", "STOP_", "CLOSE_", "REDUCE_")):
        return "Exit"
    raise ValueError("unknown order role")


def adapt_order(row):
    episode = pick(row, "ep_id", "episode_id", "포지션ID")
    if episode is None:
        raise ValueError("missing episode id")
    episode = str(episode).removesuffix(".0")
    source_label = pick(row, "event", "classified_event")
    role = role_of(pick(row, "role", "raw_role", "역할", "event"))
    order_id = pick(row, "orderid", "source_orderid", "order_id", "주문ID")
    if not order_id:
        raise ValueError("missing original order id; cannot safely deduplicate")
    stamp = pick(row, "event_time_assumed_utc", "event_time_utc", "first_time", "first", "t_first", "주문첫체결_원문시각")
    first = time_us(stamp)
    end_stamp = pick(row, "last_time", "last", "t_last", "주문마지막체결_원문시각")
    last = time_us(end_stamp) if end_stamp else first
    if last < first:
        raise ValueError("last fill precedes first fill")
    direction = str(pick(row, "direction", "방향") or "")
    if direction.lower() in {"long", "롱"}:
        direction = "Long"
    elif direction.lower() in {"short", "숏"}:
        direction = "Short"
    elif source_label:
        direction = "Short" if "SHORT" in source_label.upper() else "Long" if "LONG" in source_label.upper() else ""
    else:
        direction = ""
    symbol = str(pick(row, "symbol", "contract", "계약") or ("XBTUSD" if "bitmex_vwap" in row else ""))
    pair = pick(row, "reference_pair", "pair")
    if not pair:
        pair = "BTCUSDT" if symbol.startswith("XBT") else "ETHUSDT" if symbol == "ETHUSD" else None
    qty = number(pick(row, "qty", "quantity", "해당주문체결수량"))
    if qty is None or qty <= 0 or qty != int(qty):
        raise ValueError("positive integral contract quantity required")
    phase = row.get("phase", "first")
    first_price = number(pick(row, "bitmex_first_fill", "execution_price", "first_price", "price_first"))
    avg = number(pick(row, "bitmex_vwap", "vwap", "산술가중체결가격"))
    if first_price is not None and first_price <= 0 or avg is not None and avg <= 0:
        raise ValueError("nonpositive execution price")
    basis = number(pick(row, "avg_basis_before", "basis_before", "avg_before", "첫체결직전평균단가"))
    result = {
        "id": key_for(episode, role, order_id), "episode_id": episode, "order_id": str(order_id),
        "symbol": symbol, "pair": pair, "direction": direction, "role": role,
        "first_us": first, "last_us": last, "first_observed": phase != "last",
        "last_observed": phase == "last" or bool(end_stamp),
        "first_price": first_price if phase != "last" else None,
        "last_price": first_price if phase == "last" else number(row.get("last_price")),
        "avg_price": avg, "inverse_price": number(pick(row, "inverse_vwap", "逆", "역수가중체결가격")),
        "qty": int(qty), "position_before": number(pick(row, "qty_before", "q_before", "pos_before", "첫체결직전보유수량")),
        "position_after": number(pick(row, "qty_after", "q_after", "pos_after", "마지막체결직후보유수량")),
        "basis_before": basis, "order_type": pick(row, "ordtype", "order_type", "주문유형"),
        "stop_trigger": number(pick(row, "stop_trigger", "stop_px", "스톱발동가격")),
        "legacy_label": source_label, "legacy_reason": pick(row, "classification_reason", "classification_reason_text"),
        "episode_pnl_btc": number(row.get("episode_net_pnl_btc")),
        "context": {}, "features": {},
    }
    if phase != "last":
        for k, value in row.items():
            if not k.startswith("pre_") or value in (None, ""):
                continue
            try:
                parsed = number(value)
            except (ValueError, TypeError):
                parsed = value
            (result["features"] if "pre_1m_body_pct" in row else result["context"])[k] = parsed
    return result


def merge_order(old, new):
    if not old:
        return new
    out = dict(old)
    for name, value in new.items():
        if name in {"first_us", "last_us", "first_observed", "last_observed", "context", "features", "sources"}:
            continue
        if value is not None and value != "":
            out[name] = value
    # A last endpoint must never masquerade as a first fill.
    if new.get("first_observed") and (not old.get("first_observed") or new["first_us"] <= old["first_us"]):
        out["first_us"] = new["first_us"]
        out["first_price"] = new.get("first_price") or old.get("first_price")
    out["last_us"] = max(old["last_us"], new["last_us"])
    out["first_observed"] = bool(old.get("first_observed") or new.get("first_observed"))
    out["last_observed"] = bool(old.get("last_observed") or new.get("last_observed"))
    for field in ("context", "features"):
        out[field] = {**old.get(field, {}), **new.get(field, {})}
    out["sources"] = list(dict.fromkeys(old.get("sources", []) + new.get("sources", [])))
    return out


def present_order(order):
    r = dict(order)
    r["time"] = r["first_us"] // 1_000_000
    r["end_time"] = r["last_us"] // 1_000_000
    r["time_utc"] = iso(r["first_us"])
    r["end_time_utc"] = iso(r["last_us"])
    r["price"] = r.get("first_price") or r.get("avg_price")
    r["price_basis"] = "first_fill" if r.get("first_price") else "group_arithmetic_vwap"
    basis = r.get("basis_before")
    px = r.get("avg_price") or r.get("first_price")
    sign = 1 if r.get("direction") == "Long" else -1 if r.get("direction") == "Short" else 0
    deviation = sign * (px / basis - 1) * 100 if sign and px and basis and basis > 0 else None
    r["price_move_pct"] = deviation  # Gross price movement, never account or fee-adjusted return.
    before, after = r.get("position_before"), r.get("position_after")
    if r["role"] == "Entry":
        action = "ENTRY" if before == 0 else "ADD" if before is not None else "INCREASE"
    elif "stop" in str(r.get("order_type") or "").lower():
        action = "STOP"
    elif after == 0 and r.get("last_observed"):
        action = "CLOSE"
    elif deviation is not None and deviation > 0:
        action = "TP"
    elif deviation is not None and deviation < 0:
        action = "LOSS_REDUCE"
    else:
        action = "REDUCE"
    r["action"] = action
    warnings = []
    if before is not None and after is not None:
        delta = r["qty"] if r["role"] == "Entry" else -r["qty"]
        if not math.isclose(before + delta, after, abs_tol=0.01):
            warnings.append("주문 사이 다른 체결이 섞인 끝점: 전후 수량 차이 ≠ 이 주문 수량. 순간 보유량으로 해석 금지")
    if not r.get("first_observed"):
        warnings.append("첫 체결 끝점 미확보")
    if not r.get("last_observed"):
        warnings.append("마지막 체결시각 미확보")
    if r.get("legacy_label"):
        warnings.append("기존 연구 분류는 사후 최대 노출/휴리스틱을 포함할 수 있음. 실제 주문 유형과 별개")
    if r["last_us"] > r["first_us"]:
        warnings.append("분할체결 주문: 표시 수량·평균가격은 주문 전체 사후 합계")
    r["warnings"] = warnings
    r["timezone_status"] = "source_assumed_UTC"
    return r


def validate_bar(pair, t, o, h, low, c, volume):
    values = tuple(float(x) for x in (o, h, low, c, volume))
    if not pair or not str(pair).isalnum() or len(str(pair)) > 24:
        raise ValueError("invalid market pair")
    if t != int(t) or int(t) % 60 or not 1_400_000_000 <= int(t) <= 4_102_444_800:
        raise ValueError("invalid/alignment of 1m timestamp")
    o, h, low, c, volume = values
    if not all(math.isfinite(v) for v in values) or min(o, h, low, c) <= 0 or volume < 0:
        raise ValueError("non-finite/negative OHLCV")
    if not low <= min(o, c) <= max(o, c) <= h:
        raise ValueError("invalid OHLC order")
    return (str(pair), int(t), o, h, low, c, volume)


def aggregate(rows, seconds, start, end):
    """Strict clock-aligned complete bars only. Missing minutes become whitespace."""
    if seconds not in TIMEFRAMES.values():
        raise ValueError("unsupported timeframe")
    buckets = {}
    for row in rows:
        t, o, h, low, c, v = row
        bucket = int(t) // seconds * seconds
        buckets.setdefault(bucket, []).append((int(t), o, h, low, c, v))
    bars, missing = [], 0
    for bucket in range(start // seconds * seconds, end, seconds):
        points = sorted(buckets.get(bucket, []))
        required = seconds // 60
        complete = len(points) == required and all(p[0] == bucket + i * 60 for i, p in enumerate(points))
        if not complete:
            bars.append({"time": bucket})
            missing += 1
            continue
        bars.append({"time": bucket, "open": points[0][1], "high": max(p[2] for p in points),
                     "low": min(p[3] for p in points), "close": points[-1][4], "volume": sum(p[5] for p in points)})
    return bars, missing
