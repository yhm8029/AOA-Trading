"""Public historical OHLCV integration probe. No AOA orders or private files used."""
import json
import tempfile
from pathlib import Path
from aoa.market import fetch_window
from aoa.review import ReviewStore
from aoa.model import time_us

out=Path('test-results');out.mkdir(exist_ok=True)
report={'private_trade_data_used':False,'market':'Binance BTCUSDT spot','purpose':'2021-01-03 real 1m gap repair/5m aggregation probe; not full AOA audit'}
try:
    with tempfile.TemporaryDirectory() as d:
        store=ReviewStore(d)
        start=time_us('2021-01-03T12:00:00Z')//1_000_000;end=time_us('2021-01-03T21:00:00Z')//1_000_000
        received=fetch_window(store,'BTCUSDT',start,end)
        before=store.candles('BTCUSDT','5m',start,end)
        # Remove only the working-copy sample minutes to exercise real repair.
        with store.connect() as db:db.execute('DELETE FROM candles WHERE pair=? AND t>=? AND t<?',('BTCUSDT',start+240*60,start+420*60))
        gap=store.candles('BTCUSDT','5m',start,end)
        repaired=fetch_window(store,'BTCUSDT',start,end)
        after=store.candles('BTCUSDT','5m',start,end)
        assert before['bars']==after['bars'],'Public response changed during integration probe'
        report.update(status='passed',initial=received,repaired=repaired,initial_complete_5m=before['complete_bars'],gap_complete_5m=gap['complete_bars'],repaired_complete_5m=after['complete_bars'],remaining_missing_5m=after['missing_bars'])
except Exception as exc:
    report.update(status='unavailable_or_failed',error=str(exc))
    raise
finally:
    (out/'public-market-probe.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
