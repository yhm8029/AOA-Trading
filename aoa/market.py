"""User-triggered, bounded, public-market-only downloader; no account endpoints."""
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from .model import validate_bar
from .store import Store

BASE='https://data-api.binance.vision/api/v3/klines'


def fetch_window(store,pair,start,end,progress=lambda x:None,opener=urllib.request.urlopen):
    if not re.fullmatch(r'[A-Z0-9]{5,20}',pair):
        raise ValueError('Invalid pair')
    start=int(start)//60*60; end=(int(end)+59)//60*60
    if start<1_400_000_000 or end>int(time.time()) or not 0<end-start<=20000*60:
        raise ValueError('수동 다운로드는 과거 20,000분 이내로 좁혀 주세요. 넓은 범위는 월별 ZIP을 가져오세요.')
    total=0; cursor=start; responses=[]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        while cursor<end:
            query=urllib.parse.urlencode({'symbol':pair,'interval':'1m','startTime':cursor*1000,'endTime':end*1000-1,'limit':1000})
            request=urllib.request.Request(BASE+'?'+query,headers={'User-Agent':'AOA-Whale-Viewer/0.1'})
            raw=None
            for attempt in range(4):
                try:
                    with opener(request,timeout=30) as response:
                        raw=response.read(2*1024*1024)
                    break
                except urllib.error.HTTPError as exc:
                    if exc.code in (418,451):
                        raise ValueError('거래소 접근 제한입니다. 우회하지 않고 중단합니다. 로컬 캔들 ZIP을 사용하세요.') from None
                    if exc.code not in (429,500,502,503,504) or attempt==3:
                        raise ValueError('공개 시세 다운로드 HTTP '+str(exc.code)) from None
                    time.sleep(min(30,int(exc.headers.get('Retry-After','2'))+2**attempt))
                except (urllib.error.URLError,TimeoutError):
                    if attempt==3:
                        raise ValueError('네트워크 오류. 기존 로컬 데이터는 보존됩니다.') from None
                    time.sleep(2**attempt)
            rows=json.loads(raw)
            if not isinstance(rows,list):
                raise ValueError('Invalid market response')
            responses.append(hashlib.sha256(raw).hexdigest())
            if not rows:
                break
            last=-1
            for r in rows:
                t=int(r[0])//1000
                if int(r[0])%60000 or int(r[6])!=int(r[0])+59999 or t<=last or t<cursor or t>=end:
                    raise ValueError('Invalid market timestamp ordering')
                last=t
                Store.candle(db,validate_bar(pair,t,*r[1:6]),'binance-public-api')
                total+=1
            cursor=last+60
            progress({'message':f'{pair}: {total:,}분봉 다운로드','counts':{'received':total}})
            time.sleep(0.15)
        report={'pair':pair,'start':start,'end':end,'received':total,'response_sha256':responses,'url':BASE}
        stamp=hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest()
        db.execute('INSERT OR IGNORE INTO imports(sha256,name,report) VALUES(?,?,?)',(stamp,'Binance '+pair,json.dumps(report)))
        db.commit()
    return report
