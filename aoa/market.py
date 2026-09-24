"""Gap-only public market downloader. Network waits never hold SQLite write locks."""
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from .model import validate_bar
from .store import Store
from .review import checked_range, missing_plan

BASE='https://data-api.binance.vision/api/v3/klines'


def fetch_window(store,pair,start,end,progress=lambda x:None,opener=urllib.request.urlopen):
    start,end=checked_range(pair,start,end,historical=True)
    plan=missing_plan(store,pair,start,end)
    chunks=[]
    for a,b in plan['ranges']:
        while a<b:
            stop=min(b,a+1000*60);chunks.append((a,stop));a=stop
    counts=Counter();receipts=[]
    for index,(a,b) in enumerate(chunks):
        progress({'message':f'{pair} 실제 누락 분봉 보완 {index+1}/{len(chunks)}',
                  'progress':round(100*index/max(1,len(chunks))), 'counts':dict(counts)})
        query=urllib.parse.urlencode({'symbol':pair,'interval':'1m','startTime':a*1000,'endTime':b*1000-1,'limit':1000})
        request=urllib.request.Request(BASE+'?'+query,headers={'User-Agent':'AOA-Whale-Viewer/0.2'})
        raw=None
        for attempt in range(4):
            try:
                with opener(request,timeout=30) as response:
                    raw=response.read(2*1024*1024+1)
                if len(raw)>2*1024*1024:
                    raise ValueError('공개 시세 응답 크기 초과')
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (403,418,451):
                    raise ValueError('거래소 접근 제한: 우회하지 않고 중단했습니다. 기존 캔들은 보존됩니다. 로컬 월별 ZIP을 가져오세요.') from None
                if exc.code not in (429,500,502,503,504) or attempt==3:
                    raise ValueError('공개 시세 다운로드 HTTP '+str(exc.code)) from None
                try: delay=max(2**attempt,float(exc.headers.get('Retry-After','2')))
                except (ValueError,TypeError): delay=60
                if delay>60:
                    raise ValueError(f'거래소 요청 제한: 최소 {delay:.0f}초 후 다시 시도하세요.') from None
                time.sleep(delay)
            except (urllib.error.URLError,TimeoutError):
                if attempt==3:
                    raise ValueError('네트워크 오류. 이미 저장한 실제 분봉은 보존했습니다. 다시 보완하면 남은 구간만 요청합니다.') from None
                time.sleep(2**attempt)
        rows=json.loads(raw)
        if not isinstance(rows,list) or len(rows)>1000:
            raise ValueError('잘못된 공개 시세 응답')
        bars=[];last=a-60
        for row in rows:
            if not isinstance(row,list) or len(row)<12:
                raise ValueError('공개 시세 12열 형식 오류')
            opened=int(row[0]);t=opened//1000
            if opened%60000 or int(row[6])!=opened+59999 or not a<=t<b or t<=last:
                raise ValueError('공개 시세 시각/정렬 오류')
            bars.append(validate_bar(pair,t,*row[1:6]));last=t
        progress({'message':f'{pair} 검증한 실제 {len(bars):,}분봉 저장 중', 'counts':dict(counts)})
        receipt={'pair':pair,'start':a,'end':b,'received':len(bars),'response_sha256':hashlib.sha256(raw).hexdigest(),'url':BASE}
        digest=hashlib.sha256(json.dumps(receipt,sort_keys=True).encode()).hexdigest()
        with store.connect() as db:
            for bar in bars:
                counts[Store.candle(db,bar,'binance-public-api:'+receipt['response_sha256'])]+=1
            db.execute('INSERT OR IGNORE INTO imports(sha256,name,report) VALUES(?,?,?)',
                       (digest,'Binance '+pair,json.dumps(receipt)))
        counts['received']+=len(bars);receipts.append(receipt)
        # Empty or sparse responses are real upstream gaps, not a reason to interpolate.
        if index+1<len(chunks): time.sleep(.15)
    after=missing_plan(store,pair,start,end)
    report={'pair':pair,'start':start,'end':end,'received':counts['received'],
            'requested_minutes':plan['fetchable_minutes'],'requests':len(chunks),'counts':dict(counts),
            'remaining_missing_minutes':after['missing_minutes'],'remaining_fetchable_minutes':after['fetchable_minutes'],
            'conflict_minutes':after['conflict_minutes'],'complete':after['missing_minutes']==0,
            'response_sha256':[x['response_sha256'] for x in receipts], 'url':BASE,
            'interpolated':False,'source':'Binance spot public API'}
    progress({'message':'보완 완료' if report['complete'] else '보완 종료: 원본 공백/충돌이 남아 있습니다.',
              'progress':100,'counts':dict(counts)})
    return report
