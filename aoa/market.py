"""Opt-in public-market backfill. Sends only symbol and time range, never orders."""
from __future__ import annotations
import hashlib
import json
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from .model import clean_symbol, candle
from .store import put_candle, rebuild

HOST='https://data-api.binance.vision/api/v3/klines'


def fetch_public(store,pair,start,end,cache_dir,progress=lambda text:None,opener=urlopen):
    pair=clean_symbol(pair)
    if not pair.endswith(('USDT','BTC','USDC')):
        raise ValueError('Unsupported public-market pair')
    start=int(start)//60*60;end=(int(end)+59)//60*60
    now=int(time.time())//60*60
    if start<1262304000 or end<=start or end>now or end-start>32*86400:
        raise ValueError('과거의 최대 32일 범위를 선택하세요. 미래/진행 중 분봉은 수집하지 않습니다.')
    cache_dir.mkdir(parents=True,exist_ok=True)
    current=start
    counts={'fetched':0,'inserted':0,'duplicate':0,'conflict':0,'pages':0}
    digest=hashlib.sha256()
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        while current<end:
            url=HOST+'?'+urlencode(dict(symbol=pair,interval='1m',startTime=current*1000,endTime=end*1000-1,limit=1000))
            payload=None
            for attempt in range(3):
                try:
                    with opener(Request(url,headers={'User-Agent':'AOA-Whale-Viewer/0.1'}),timeout=25) as response:
                        body=response.read(2000000)
                    payload=json.loads(body)
                    break
                except HTTPError as e:
                    if e.code in (418,429,451):
                        raise ValueError(f'시장 서버 요청 제한/지역 제한 HTTP {e.code}. 우회하지 않고 중단합니다. 로컬 원본 캔들 ZIP을 사용하세요.') from e
                    if attempt==2:
                        raise
                    time.sleep(1+attempt)
            if not isinstance(payload,list):
                raise ValueError('Unexpected Binance response')
            if not payload:
                break
            last=current-60
            for r in payload:
                if len(r)<12 or int(r[0])%60000 or int(r[6])!=int(r[0])+59999:
                    raise ValueError('Invalid Binance kline timestamp')
                t=int(r[0])//1000
                if t<current or t>=end or t<=last:
                    raise ValueError('Unsorted/out-of-range Binance data')
                item=candle(dict(reference_pair=pair,time=t,open=r[1],high=r[2],low=r[3],close=r[4],volume=r[5]))
                state=put_candle(db,item,'Binance public API (opt-in)')
                counts[state]+=1;counts['fetched']+=1;last=t
            page_hash=hashlib.sha256(body).hexdigest()
            (cache_dir/(page_hash+'.json')).write_bytes(body)
            digest.update(body)
            counts['pages']+=1
            progress(f'{pair} 공개 분봉 {counts["fetched"]:,}개 수집')
            if last<current:
                raise ValueError('Pagination did not advance')
            current=last+60
            if counts['pages']>48:
                raise ValueError('Pagination safety cap reached')
            time.sleep(.15)
        rebuild(db,{pair},progress)
        report={**counts,'pair':pair,'start':start,'end':end,
            'requested_minutes':(end-start)//60,'network_source':HOST,
            'contains_trader_data':False,'finished_utc':datetime.now(timezone.utc).isoformat()}
        db.execute('INSERT OR IGNORE INTO imports(hash,name,report) VALUES(?,?,?)',
            (digest.hexdigest(),f'Public market {pair} {start}-{end}',json.dumps(report)))
    return report
