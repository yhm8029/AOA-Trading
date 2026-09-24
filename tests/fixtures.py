"""Small deterministic SYNTHETIC fixtures. These are NOT AOA trade records."""
from __future__ import annotations
import csv
import gzip
import io
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path

START = 1622764800  # Synthetic data begins 2021-06-04 00:00 UTC.


def csv_bytes(rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8-sig')


def bars(count=360, start=START):
    result = []
    for i in range(count):
        o = round(100 + math.sin(i / 17) * 4 + i * .003, 5)
        c = round(o + math.sin(i / 3) * .25, 5)
        result.append(dict(reference_pair='BTCUSDT', minute_utc=(start + i * 60)//60,
                           open=o, high=round(max(o,c)+.5,5), low=round(min(o,c)-.5,5),
                           close=c, volume=round(5 + (i % 23) * .3,5)))
    return result


def event(**override):
    row = dict(event_id='SYNTHETIC-001', episode_id='900001',
               event_time_utc='2021-06-04 01:00:15.123456', event='ENTRY_SHORT',
               direction='Short', qty=1000000, bitmex_vwap=103.25, bitmex_first_fill=103.2,
               qty_before=0, qty_after=1000000, avg_basis_before=0,
               episode_max_qty=1500000, stop_trigger='', episode_net_pnl_btc=.012,
               classification_reason='SYNTHETIC TEST ONLY; not a real whale trade',
               source_orderid='SYNTHETIC-order-001', symbol='XBTUSD', reference_pair='BTCUSDT')
    row.update(override)
    return row


def events():
    return [event(),
       event(event_id='SYNTHETIC-002',source_orderid='SYNTHETIC-order-002',
             event_time_utc='2021-06-04 01:02:30',event='ADD_SHORT',qty=500000,
             qty_before=1000000,qty_after=1500000,avg_basis_before=103.25,bitmex_first_fill=104,bitmex_vwap=104),
       event(event_id='SYNTHETIC-003',source_orderid='SYNTHETIC-order-003',
             event_time_utc='2021-06-04 01:45:30',event='TAKE_PROFIT_SHORT',qty=700000,
             qty_before=1500000,qty_after=800000,avg_basis_before=103.5,bitmex_first_fill=99,bitmex_vwap=99),
       event(event_id='SYNTHETIC-004',source_orderid='SYNTHETIC-order-004',
             event_time_utc='2021-06-04 02:00:10',event='CLOSE_SHORT',qty=800000,
             qty_before=800000,qty_after=0,avg_basis_before=103.5,bitmex_first_fill=100,bitmex_vwap=100),
       event(event_id='SYNTHETIC-005',episode_id='900002',source_orderid='SYNTHETIC-order-005',
             event_time_utc='2021-06-04 03:00:00',event='ENTRY_LONG',direction='Long',
             qty=400000,qty_before=0,qty_after=400000,episode_net_pnl_btc=-.004),
       event(event_id='SYNTHETIC-006',episode_id='900002',source_orderid='SYNTHETIC-order-006',
             event_time_utc='2021-06-04 04:00:00',event='STOP_LONG',direction='Long',
             qty=400000,qty_before=400000,qty_after=0,avg_basis_before=104,
             bitmex_first_fill=100,bitmex_vwap=99.8,stop_trigger=100.5,episode_net_pnl_btc=-.004)]


def package(path: Path, count=1500):
    """Structure mirrors an AOA candle/event ZIP but all values are invented test data."""
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('events.csv',csv_bytes(events()))
        z.writestr('candles_1m.csv.gz',gzip.compress(csv_bytes(bars(count))))
        z.writestr('README_SYNTHETIC.txt','SYNTHETIC TEST FIXTURE - NOT AOA DATA')
    return path
