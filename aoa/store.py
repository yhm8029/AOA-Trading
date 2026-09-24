"""Local SQLite with immutable source provenance and complete-bar aggregation."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from .model import TIMEFRAMES

SCHEMA = '''
CREATE TABLE IF NOT EXISTS events(
 id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, symbol TEXT NOT NULL,
 direction TEXT NOT NULL, time_us INTEGER NOT NULL, end_us INTEGER,
 event TEXT NOT NULL, qty INTEGER NOT NULL, priority INTEGER NOT NULL,
 pnl REAL, max_qty INTEGER, pair TEXT, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_episode ON events(symbol,episode_id,time_us);
CREATE INDEX IF NOT EXISTS events_time ON events(time_us);
CREATE TABLE IF NOT EXISTS candles(
 pair TEXT NOT NULL, time INTEGER NOT NULL, open REAL NOT NULL,
 high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL, volume REAL NOT NULL,
 source TEXT NOT NULL, PRIMARY KEY(pair,time)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS conflicts(pair TEXT, time INTEGER, reason TEXT, PRIMARY KEY(pair,time));
CREATE TABLE IF NOT EXISTS bars(
 pair TEXT NOT NULL, tf INTEGER NOT NULL, time INTEGER NOT NULL,
 open REAL, high REAL, low REAL, close REAL, volume REAL,
 PRIMARY KEY(pair,tf,time)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS imports(
 hash TEXT PRIMARY KEY, name TEXT NOT NULL, report TEXT NOT NULL, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS quarantine(
 source TEXT, row_number INTEGER, reason TEXT, raw TEXT);
CREATE TABLE IF NOT EXISTS notes(
 episode_key TEXT PRIMARY KEY, body TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 updated TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT);
'''


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO metadata VALUES('revision','0')")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=60)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=60000')
        return db

    def stats(self):
        with self.connect() as db:
            return dict(events=db.execute('SELECT count(*) FROM events').fetchone()[0],
                episodes=db.execute('SELECT count(*) FROM (SELECT 1 FROM events GROUP BY symbol,episode_id)').fetchone()[0],
                minute_bars=db.execute('SELECT count(*) FROM candles').fetchone()[0],
                quarantined=db.execute('SELECT count(*) FROM quarantine').fetchone()[0],
                conflicting_minutes=db.execute('SELECT count(*) FROM conflicts').fetchone()[0],
                revision=db.execute("SELECT value FROM metadata WHERE key='revision'").fetchone()[0],
                imports=[dict(r) for r in db.execute('SELECT name,report,created FROM imports ORDER BY created DESC LIMIT 15')],
                pairs=[dict(r) for r in db.execute('SELECT pair,min(time) AS start,max(time) AS end,count(*) AS bars FROM candles GROUP BY pair')])

    def events(self, symbol, episode_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM events WHERE symbol=? AND episode_id=? ORDER BY time_us,id',(symbol,str(episode_id)))]

    def episodes(self):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute('''SELECT symbol,episode_id,direction,
             min(time_us) AS start_us,max(coalesce(end_us,time_us)) AS end_us,
             count(*) AS event_count,max(max_qty) AS max_qty,min(pnl) AS pnl_min,
             max(pnl) AS pnl_max,max(pair) AS pair FROM events
             GROUP BY symbol,episode_id,direction ORDER BY start_us''')]
        for r in rows:
            r['net_pnl_btc'] = r.pop('pnl_min') if r['pnl_min'] == r['pnl_max'] else None
            r.pop('pnl_max')
            r.pop('pnl_min', None)
            r['range_basis'] = '표시 주문의 첫/마지막 끝점 범위; 원장 전체 보유기간과 다를 수 있음'
        return rows

    def chart(self, pair, tf, start, end):
        if tf not in TIMEFRAMES:
            raise ValueError('Unsupported timeframe')
        step = tf * 60
        start = (int(start) // step) * step
        end = ((int(end) + step - 1) // step) * step
        if end <= start or (end-start)//step > 10000:
            raise ValueError('한 번에 최대 10,000봉. 더 큰 시간봉 또는 좁은 범위를 선택하세요.')
        with self.connect() as db:
            if tf == 1:
                rows = db.execute('SELECT time,open,high,low,close,volume,source FROM candles WHERE pair=? AND time>=? AND time<? ORDER BY time',(pair,start,end)).fetchall()
            else:
                rows = db.execute('SELECT time,open,high,low,close,volume FROM bars WHERE pair=? AND tf=? AND time>=? AND time<? ORDER BY time',(pair,tf,start,end)).fetchall()
        data = {r['time']:dict(r) for r in rows}
        points, missing = [], 0
        for t in range(start,end,step):
            if t in data:
                points.append(data[t])
            else:
                points.append({'time':t})
                missing += 1
        return dict(pair=pair, timeframe=tf, start=start, end=end, bars=points,
                    expected=len(points), valid=len(data), missing=missing,
                    proxy='Binance spot OHLCV; not BitMEX execution prices or volume',
                    aggregation='UTC left-closed intervals; complete 1m groups only; no interpolation')

    def event_volume(self, event):
        """Separate pre-decision complete volume from retrospective event-minute volume."""
        t = event['time_us'] // 60000000 * 60
        pair = event['reference_pair']
        with self.connect() as db:
            current = db.execute('SELECT volume FROM candles WHERE pair=? AND time=?',(pair,t)).fetchone()
            pre = db.execute('SELECT time,volume FROM candles WHERE pair=? AND time>=? AND time<? ORDER BY time',(pair,t-21*60,t)).fetchall()
        prior = {r['time']:r['volume'] for r in pre}
        last = prior.get(t-60)
        reference = [prior.get(m) for m in range(t-21*60,t-60,60)]
        avg = sum(reference)/20 if all(v is not None for v in reference) else None
        ratio = last/avg if last is not None and avg and avg>0 else None
        before20 = [prior.get(m) for m in range(t-20*60,t,60)]
        avg2 = sum(before20)/20 if all(v is not None for v in before20) else None
        return dict(pre_1m_volume=last,pre_1m_rvol20=ratio,
            event_minute_final_volume=current[0] if current else None,
            event_minute_final_rvol20=current[0]/avg2 if current and avg2 and avg2>0 else None,
            event_minute_is_retrospective=True, volume_unit='BTC' if pair=='BTCUSDT' else 'base asset')

    def note(self,key):
        with self.connect() as db:
            r=db.execute('SELECT body,version,updated FROM notes WHERE episode_key=?',(key,)).fetchone()
        return dict(r) if r else dict(body='',version=0,updated=None)

    def save_note(self,key,body,version):
        if len(body)>20000 or len(key)>120:
            raise ValueError('Note too long')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            r=db.execute('SELECT version FROM notes WHERE episode_key=?',(key,)).fetchone()
            actual=r[0] if r else 0
            if version != actual:
                raise ValueError('다른 창에서 메모가 변경됐습니다. 새로 읽고 저장하세요.')
            db.execute('INSERT INTO notes VALUES(?,?,?,CURRENT_TIMESTAMP) ON CONFLICT(episode_key) DO UPDATE SET body=excluded.body,version=excluded.version,updated=excluded.updated',(key,body,actual+1))
        return self.note(key)


def put_event(db,e,priority):
    row=db.execute('SELECT priority,payload FROM events WHERE id=?',(e['id'],)).fetchone()
    old=json.loads(row['payload']) if row else None
    if e.get('phase') == 'last':
        if old:
            old['end_time_us']=e['time_us']
            old['last_price']=e.get('first_price')
            old['event_end_utc']=e['event_time_utc']
            e=old
            priority=row['priority']
        else:
            return False
    elif old:
        contexts={**old.get('context',{}),**e.get('context',{})}
        if priority < row['priority']:
            merged={**e,**old}
            for k,v in e.items():
                if merged.get(k) is None and v is not None:
                    merged[k]=v
            e=merged
            priority=row['priority']
        else:
            e={**old,**{k:v for k,v in e.items() if v is not None}}
        e['context']=contexts
        e['warnings']=sorted(set(old.get('warnings',[])+e.get('warnings',[])))
    db.execute('''INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
     ON CONFLICT(id) DO UPDATE SET time_us=excluded.time_us,end_us=excluded.end_us,
     event=excluded.event,qty=excluded.qty,priority=excluded.priority,pnl=excluded.pnl,
     max_qty=excluded.max_qty,pair=excluded.pair,payload=excluded.payload''',
     (e['id'],e['episode_id'],e['symbol'],e['direction'],e['time_us'],e.get('end_time_us'),e['event'],e['qty'],priority,e.get('episode_net_pnl_btc'),e.get('episode_max_qty'),e.get('reference_pair'),json.dumps(e,ensure_ascii=False,allow_nan=False)))
    return not bool(old)


def put_candle(db,c,source):
    pair,t,*values=c
    if db.execute('SELECT 1 FROM conflicts WHERE pair=? AND time=?',(pair,t)).fetchone():
        return 'conflict'
    old=db.execute('SELECT open,high,low,close,volume FROM candles WHERE pair=? AND time=?',(pair,t)).fetchone()
    if old:
        if tuple(old)==tuple(values):
            return 'duplicate'
        db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(pair,t,'Conflicting OHLCV: all variants excluded'))
        db.execute('DELETE FROM candles WHERE pair=? AND time=?',(pair,t))
        return 'conflict'
    db.execute('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?)',(*c,source))
    return 'inserted'


def rebuild(db,pairs,progress=lambda text:None):
    """Only fully populated fixed UTC intervals can become candles."""
    for pair in sorted(pairs):
        progress(f'{pair}: 5m/15m/1h/4h/1d 집계')
        db.execute('DELETE FROM bars WHERE pair=?',(pair,))
        accum={}
        batch=[]
        def finish(tf,a):
            if a and a[6] == tf and a[7]-a[0] == (tf-1)*60:
                batch.append((pair,tf,*a[:6]))
        cursor=db.execute('SELECT time,open,high,low,close,volume FROM candles WHERE pair=? ORDER BY time',(pair,))
        for r in cursor:
            t,o,h,l,c,v=tuple(r)
            for tf in TIMEFRAMES[1:]:
                start=t//(tf*60)*(tf*60)
                a=accum.get(tf)
                if a is None or a[0]!=start:
                    finish(tf,a)
                    accum[tf]=[start,o,h,l,c,v,1,t]
                else:
                    a[2]=max(a[2],h);a[3]=min(a[3],l);a[4]=c;a[5]+=v;a[6]+=1;a[7]=t
            if len(batch)>=5000:
                db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',batch)
                batch.clear()
        for tf,a in accum.items():
            finish(tf,a)
        if batch:
            db.executemany('INSERT INTO bars VALUES(?,?,?,?,?,?,?,?)',batch)
    db.execute("UPDATE metadata SET value=CAST(value AS INTEGER)+1 WHERE key='revision'")
