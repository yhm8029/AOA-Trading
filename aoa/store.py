from __future__ import annotations
import json
import math
import sqlite3
from pathlib import Path
from .model import merge_order, present_order, TIMEFRAMES, aggregate

SCHEMA = '''
CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, episode TEXT NOT NULL, symbol TEXT, direction TEXT, t INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS orders_episode ON orders(episode,t);
CREATE INDEX IF NOT EXISTS orders_symbol_time ON orders(symbol,t);
CREATE TABLE IF NOT EXISTS candles (pair TEXT, t INTEGER, o REAL, h REAL, l REAL, c REAL, v REAL, source TEXT, PRIMARY KEY(pair,t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS conflicts (pair TEXT, t INTEGER, reason TEXT, PRIMARY KEY(pair,t)) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS imports (sha256 TEXT PRIMARY KEY, name TEXT, report TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS issues (id INTEGER PRIMARY KEY, source TEXT, line INTEGER, reason TEXT);
CREATE TABLE IF NOT EXISTS notes (episode TEXT PRIMARY KEY, text TEXT NOT NULL, tags TEXT NOT NULL, updated TEXT DEFAULT CURRENT_TIMESTAMP);
PRAGMA user_version=1;
'''

class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'viewer.sqlite3'
        with self.connect() as db:
            db.executescript(SCHEMA)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=45)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=45000')
        return db

    @staticmethod
    def order(db, item, source):
        old = db.execute('SELECT payload FROM orders WHERE id=?', (item['id'],)).fetchone()
        item['sources'] = [source]
        item = merge_order(json.loads(old[0]) if old else None, item)
        if item.get('last_us', 0) < item['first_us']:
            item['last_us'] = item['first_us']
        db.execute('INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?,?)',
                   (item['id'], item['episode_id'], item.get('symbol'), item.get('direction'), item['first_us'], json.dumps(item, ensure_ascii=False, allow_nan=False)))

    @staticmethod
    def candle(db, bar, source):
        pair, t, *values = bar
        if db.execute('SELECT 1 FROM conflicts WHERE pair=? AND t=?', (pair,t)).fetchone():
            return 'blocked'
        old = db.execute('SELECT o,h,l,c,v FROM candles WHERE pair=? AND t=?', (pair,t)).fetchone()
        if old:
            if all(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-8) for a,b in zip(old,values)):
                return 'duplicate'
            db.execute('DELETE FROM candles WHERE pair=? AND t=?', (pair,t))
            db.execute('INSERT INTO conflicts VALUES(?,?,?)', (pair,t,'Conflicting OHLCV: both observations quarantined'))
            return 'conflict'
        db.execute('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?)', (*bar,source))
        return 'inserted'

    def status(self):
        with self.connect() as db:
            rows = db.execute('SELECT pair,COUNT(*) AS bars,MIN(t) AS start,MAX(t) AS end FROM candles GROUP BY pair').fetchall()
            return {'orders': db.execute('SELECT COUNT(*) FROM orders').fetchone()[0],
                    'episodes': db.execute('SELECT COUNT(DISTINCT episode) FROM orders').fetchone()[0],
                    'markets': [dict(x) for x in rows],
                    'issues': db.execute('SELECT COUNT(*) FROM issues').fetchone()[0],
                    'conflicts': db.execute('SELECT COUNT(*) FROM conflicts').fetchone()[0],
                    'imports': [dict(x) for x in db.execute('SELECT name,sha256,created,report FROM imports ORDER BY created DESC LIMIT 30')]}

    def episodes(self, symbol='XBTUSD', year='', direction='', result='', search=''):
        where, args = [], []
        if symbol:
            where.append('symbol=?'); args.append(symbol)
        if direction:
            where.append('direction=?'); args.append(direction)
        if search:
            where.append('episode LIKE ?'); args.append('%'+search+'%')
        sql = 'SELECT payload FROM orders' + (' WHERE '+' AND '.join(where) if where else '') + ' ORDER BY t'
        with self.connect() as db:
            grouped = {}
            for row in db.execute(sql,args):
                o = json.loads(row[0]); ep = o['episode_id']
                if ep not in grouped:
                    grouped[ep] = {'id': ep, 'direction':o['direction'], 'symbol':o['symbol'], 'pair':o.get('pair'),
                        'start':o['first_us']//1_000_000, 'end':o['last_us']//1_000_000, 'count':0,
                        'pnl_btc':None, 'max_observed_qty':None, 'focus':None, 'closed':None}
                x=grouped[ep]; x['count']+=1; x['end']=max(x['end'],o['last_us']//1_000_000)
                if o.get('episode_pnl_btc') is not None:
                    x['pnl_btc']=o['episode_pnl_btc']
                for k in ('position_before','position_after'):
                    if o.get(k) is not None:
                        x['max_observed_qty']=max(x['max_observed_qty'] or 0,o[k])
                if x['focus'] is None and o['role']=='Entry' and o['qty'] >= 1_000_000:
                    x['focus']=o['first_us']//1_000_000
                if o.get('last_observed') and o['last_us']//1_000_000 >= x['end']:
                    x['closed']=(o.get('position_after')==0) if o.get('position_after') is not None else None
            result_rows=[]
            from datetime import datetime, timezone
            for x in grouped.values():
                x['focus']=x['focus'] or x['start']
                x['result']='Win' if x['pnl_btc'] is not None and x['pnl_btc']>0 else 'Loss' if x['pnl_btc'] is not None and x['pnl_btc']<0 else 'Flat' if x['pnl_btc']==0 else 'Unknown'
                # Include episodes overlapping selected year, not only newly opened episodes.
                if year and not (datetime.fromtimestamp(x['start'],timezone.utc).year <= int(year) <= datetime.fromtimestamp(x['end'],timezone.utc).year):
                    continue
                if result and x['result']!=result:
                    continue
                result_rows.append(x)
            return result_rows

    def events(self, episode):
        with self.connect() as db:
            return [present_order(json.loads(row[0])) for row in db.execute('SELECT payload FROM orders WHERE episode=? ORDER BY t,id',(str(episode),))]

    def candles(self, pair, timeframe, start, end):
        seconds=TIMEFRAMES[timeframe]
        start=int(start)//seconds*seconds
        end=(int(end)+seconds-1)//seconds*seconds
        if not start<end or (end-start)//seconds>4000:
            raise ValueError('한 화면은 최대 4,000봉입니다. 기간을 좁히거나 시간봉을 높이세요. 전체 보유 기록 제한은 아닙니다.')
        with self.connect() as db:
            rows=db.execute('SELECT t,o,h,l,c,v FROM candles WHERE pair=? AND t>=? AND t<? ORDER BY t',(pair,start,end))
            bars,missing=aggregate(rows,seconds,start,end)
        return {'pair':pair,'timeframe':timeframe,'start':start,'end':end,'bars':bars,'missing_bars':missing,
                'complete_bars':len(bars)-missing,'source':'Binance spot proxy','interpolated':False}

    def get_note(self,episode):
        with self.connect() as db:
            row=db.execute('SELECT text,tags,updated FROM notes WHERE episode=?',(str(episode),)).fetchone()
            return dict(row) if row else {'text':'','tags':'','updated':None}

    def save_note(self,episode,text,tags):
        if len(text)>30000 or len(tags)>1000:
            raise ValueError('메모 또는 태그가 너무 깁니다.')
        with self.connect() as db:
            db.execute('INSERT INTO notes(episode,text,tags) VALUES(?,?,?) ON CONFLICT(episode) DO UPDATE SET text=excluded.text,tags=excluded.tags,updated=CURRENT_TIMESTAMP',(str(episode),text,tags))

    def issues(self):
        with self.connect() as db:
            return [dict(x) for x in db.execute('SELECT source,line,reason FROM issues ORDER BY id DESC LIMIT 500')]
