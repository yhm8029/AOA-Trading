"""Streaming CSV/gzip/ZIP import, no extraction, no source mutations."""
from __future__ import annotations
import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from .model import adapt_order, validate_bar, time_us, number
from .store import Store

MAX_ARCHIVE_BYTES = 3 * 1024**3
MAX_MEMBERS = 10000


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def safe_members(z):
    entries=z.infolist()
    if len(entries)>MAX_MEMBERS or sum(i.file_size for i in entries)>MAX_ARCHIVE_BYTES:
        raise ValueError('압축 해제 크기 또는 파일 수 안전 한도 초과')
    for i in entries:
        name=i.filename.replace('\\','/')
        p=PurePosixPath(name)
        if name.startswith('/') or '..' in p.parts or ':' in name or (i.external_attr>>16)&0o170000==0o120000:
            raise ValueError('안전하지 않은 ZIP 경로/링크')
    return entries


def csv_kind(headers):
    cols=set(headers)
    if {'open','high','low','close','volume'} <= cols:
        return 'candles'
    if 'event_time_assumed_utc' in cols and 'role' in cols:
        return 'orders'
    if 'event_time_utc' in cols and 'source_orderid' in cols:
        return 'orders'
    if '포지션ID' in cols and '주문ID' in cols:
        return 'orders'
    if {'ep_id','role','orderid'} <= cols and any(x in cols for x in ('first','first_time','t_first')):
        return 'orders'
    return 'unknown'


def import_file(store, path, display_name=None, progress=lambda x:None):
    path=Path(path)
    digest=sha256(path)
    name=display_name or path.name
    with store.connect() as check:
        if check.execute('SELECT 1 FROM imports WHERE sha256=?',(digest,)).fetchone():
            return {'name':name,'already_imported':True,'sha256':digest}
    counts=Counter(); skipped=[]
    with store.connect() as db:
        # One transaction per selected input. Failed imports never leave half-written rows.
        db.execute('BEGIN IMMEDIATE')
        def problem(source,line,exc):
            counts['rejected_rows']+=1
            if counts['rejected_rows']<=2000:
                db.execute('INSERT INTO issues(source,line,reason) VALUES(?,?,?)',(source,line,str(exc)[:350]))
        def parse(stream,source):
            text=io.TextIOWrapper(stream,encoding='utf-8-sig',newline='')
            reader=csv.reader(text)
            first=next(reader,None)
            if not first:
                return
            raw_pair=re.search(r'([A-Z0-9]+)-1m-\d{4}-\d{2}',source)
            raw=bool(raw_pair and first[0].isdigit())
            if raw:
                kind='binance'; iterable=enumerate(_prepend(first,reader),1)
            else:
                headers=[str(x).strip() for x in first]
                kind=csv_kind(headers)
                if kind=='unknown':
                    skipped.append(source); return
                iterable=enumerate((dict(zip(headers,row)) for row in reader if row),2)
            for line,row in iterable:
                counts['rows_seen']+=1
                try:
                    if kind=='orders':
                        item=adapt_order(row)
                        Store.order(db,item,source)
                        counts['order_endpoints']+=1
                    else:
                        if kind=='binance':
                            if len(row)<12:
                                raise ValueError('Binance kline columns < 12')
                            opened=int(row[0]); unit=1_000_000 if opened>=100_000_000_000_000 else 1000
                            if opened % (60*unit) or int(row[6])!=opened+60*unit-1:
                                raise ValueError('invalid Binance kline timestamp')
                            bar=validate_bar(raw_pair.group(1),opened//unit,*row[1:6])
                        else:
                            stamp=row.get('candle_open_utc') or row.get('open_time_utc')
                            if stamp:
                                t=time_us(stamp)//1_000_000
                            elif row.get('minute_utc'):
                                t=int(row['minute_utc'])*60
                            else:
                                raise ValueError('missing normalized candle timestamp')
                            pair=row.get('reference_pair') or row.get('pair') or row.get('symbol')
                            bar=validate_bar(pair,t,*(row[k] for k in ('open','high','low','close','volume')))
                        status=Store.candle(db,bar,source)
                        counts['candles_'+status]+=1
                        if status=='conflict':
                            problem(source,line,'충돌 캔들 격리: '+str(bar[:2]))
                except (ValueError,KeyError,TypeError,OverflowError) as exc:
                    problem(source,line,exc)
                if counts['rows_seen']%2000==0:
                    progress({'message':source,'counts':dict(counts)})
        def walk(stream,source,depth=0):
            if source.lower().endswith('.zip'):
                if depth>2:
                    raise ValueError('ZIP nesting depth exceeded')
                with zipfile.ZipFile(stream) as z:
                    entries=safe_members(z)
                    # Full context first, legacy events next, detailed features last; all merge by original ID.
                    entries.sort(key=lambda i:('features' in i.filename,i.filename))
                    for info in entries:
                        if info.is_dir():
                            continue
                        suffix=info.filename.lower()
                        child=source+'/'+info.filename
                        if suffix.endswith(('.csv','.csv.gz')):
                            with z.open(info) as raw:
                                if suffix.endswith('.gz'):
                                    with gzip.GzipFile(fileobj=raw) as gz:
                                        parse(gz,child)
                                else:
                                    parse(raw,child)
                        elif suffix.endswith('.zip') and re.search(r'[A-Z0-9]+-1m-\d{4}-\d{2}',info.filename):
                            if info.file_size>64*1024**2:
                                raise ValueError('nested monthly ZIP >64MB')
                            with z.open(info) as raw:
                                walk(io.BytesIO(raw.read()),child,depth+1)
                        else:
                            skipped.append(child)
            elif source.lower().endswith('.gz'):
                with gzip.GzipFile(fileobj=stream) as gz:
                    parse(gz,source)
            else:
                parse(stream,source)
        try:
            with path.open('rb') as f:
                walk(f,name)
            if not counts['order_endpoints'] and not sum(v for k,v in counts.items() if k.startswith('candles_')):
                raise ValueError('지원되는 데이터가 없습니다. AOA_candle_analysis.zip / order_context.csv / events.csv를 선택하세요. 원본 execution ZIP은 직접 재구성하지 않습니다.')
            report={'name':name,'sha256':digest,'counts':dict(counts),'skipped_members':skipped[:120],
                    'note':'원본 미수정. CSV 사전 특징만 저장. post_*는 예측 입력에 적재하지 않음.'}
            db.execute('INSERT INTO imports(sha256,name,report) VALUES(?,?,?)',(digest,name,json.dumps(report,ensure_ascii=False)))
            db.commit()
            return report
        except Exception:
            db.rollback()
            raise


def _prepend(first,rest):
    yield first
    yield from rest
