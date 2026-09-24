"""Streaming import of existing AOA packages, no public upload or extraction."""
from __future__ import annotations
import csv
import gzip
import hashlib
import io
import itertools
import json
import re
import stat
import zipfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from .model import candle, clean_symbol, normalize_event, pick, time_us
from .store import put_candle, put_event, rebuild

MAX_FILE = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
RAW_NAME = re.compile(r'([A-Z0-9]+)-1m-\d{4}-\d{2}(?:-\d{2})?\.csv$', re.I)


def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):
            h.update(b)
    return h.hexdigest()


class LimitedReader(io.RawIOBase):
    def __init__(self,stream,limit=MAX_EXPANDED):
        self.stream=stream;self.remaining=limit
    def readable(self):
        return True
    def readinto(self,b):
        chunk=self.stream.read(min(len(b),self.remaining+1))
        self.remaining-=len(chunk)
        if self.remaining<0:
            raise ValueError('Expanded stream exceeds safety limit')
        b[:len(chunk)]=chunk
        return len(chunk)


@contextmanager
def text_stream(stream,name):
    if name.lower().endswith('.gz'):
        with gzip.GzipFile(fileobj=stream) as unzipped:
            with io.TextIOWrapper(io.BufferedReader(LimitedReader(unzipped)),encoding='utf-8-sig',newline='') as text:
                yield text
    else:
        with io.TextIOWrapper(io.BufferedReader(LimitedReader(stream)),encoding='utf-8-sig',newline='') as text:
            yield text


def safe_members(z):
    infos=z.infolist()
    if len(infos)>3000 or sum(i.file_size for i in infos)>MAX_EXPANDED:
        raise ValueError('Archive too large; split into smaller packages')
    seen=set()
    for i in infos:
        p=PurePosixPath(i.filename.replace('\\','/'))
        if p.is_absolute() or '..' in p.parts or re.match(r'^[A-Za-z]:',str(p)):
            raise ValueError('Unsafe archive member path')
        if stat.S_ISLNK(i.external_attr>>16) or i.flag_bits & 1:
            raise ValueError('Symlinks and encrypted archives are not supported')
        if i.filename in seen:
            raise ValueError('Duplicate archive member names')
        seen.add(i.filename)
    return infos


def quarantine(db,source,line,reason,row):
    db.execute('INSERT INTO quarantine VALUES(?,?,?,?)',(source,line,str(reason)[:600],json.dumps(row,ensure_ascii=False)[:4000]))


def poison_if_identifiable(db,row,pairs):
    try:
        pair=clean_symbol(pick(row,'reference_pair','pair','symbol',default='BTCUSDT'))
        if row.get('minute_utc'):
            t=int(row['minute_utc'])*60
        else:
            t=time_us(pick(row,'candle_open_utc','time','open_time','timestamp'))//1000000
        if t%60:
            return
        db.execute('INSERT OR IGNORE INTO conflicts VALUES(?,?,?)',(pair,t,'Invalid source row for known minute'))
        db.execute('DELETE FROM candles WHERE pair=? AND time=?',(pair,t))
        pairs.add(pair)
    except (ValueError,TypeError):
        pass


def read_table(db,stream,name,counts,pairs,progress):
    csv.field_size_limit(1024*1024)
    with text_stream(stream,name) as text:
        reader=csv.reader(text)
        first=next(reader,None)
        if first is None:
            counts['empty_files']+=1
            return
        raw_match=RAW_NAME.search(PurePosixPath(name).name)
        raw=bool(raw_match and re.fullmatch(r'\d+',first[0].strip()))
        headers=[v.strip() for v in first]
        event=not raw and (('event_time_utc' in headers and ('event' in headers or 'event_type' in headers)) or ('event_time_assumed_utc' in headers and 'phase' in headers))
        bars=raw or all(k in headers for k in ('open','high','low','close','volume'))
        if not event and not bars:
            counts['unsupported_tables']+=1
            return
        counts['recognized_tables']+=1
        records=itertools.chain([first],reader) if raw else reader
        for line,values in enumerate(records,1 if raw else 2):
            if line>10000000:
                raise ValueError('Row safety limit exceeded')
            row={}
            try:
                if raw:
                    if len(values)<12:
                        raise ValueError('Raw Binance row needs 12 columns')
                    opened=int(values[0]);unit=60000000 if opened>=100000000000000 else 60000
                    if opened%unit or int(values[6])!=opened+unit-1:
                        raise ValueError('Invalid Binance open/close timestamp')
                    row=dict(reference_pair=raw_match[1].upper(),minute_utc=opened//unit,
                        open=values[1],high=values[2],low=values[3],close=values[4],volume=values[5])
                else:
                    if len(values)!=len(headers):
                        raise ValueError('CSV column count mismatch')
                    row=dict(zip(headers,values))
                if bars:
                    c=candle(row)
                    state=put_candle(db,c,name)
                    counts['candles_'+state]+=1
                    pairs.add(c[0])
                else:
                    e,priority=normalize_event(row,name,line)
                    created=put_event(db,e,priority)
                    counts['events_created' if created else 'events_merged']+=1
                counts['rows_processed']+=1
            except (ValueError,TypeError,OverflowError) as exc:
                counts['invalid_rows']+=1
                quarantine(db,name,line,exc,row or values)
                if bars:
                    poison_if_identifiable(db,row,pairs)
            if line%10000==0:
                progress(f'{PurePosixPath(name).name}: {line:,}행 읽는 중')


def read_zip(db,stream,name,counts,pairs,progress,depth=0):
    with zipfile.ZipFile(stream) as z:
        for i in safe_members(z):
            if i.is_dir():
                continue
            lower=i.filename.lower()
            if lower.endswith(('.csv','.csv.gz')):
                progress(f'{PurePosixPath(i.filename).name} 읽는 중')
                with z.open(i) as f:
                    read_table(db,f,name+'!'+i.filename,counts,pairs,progress)
            elif lower.endswith('.zip') and depth<1 and i.file_size<=64*1024*1024:
                with io.BytesIO(z.read(i)) as nested:
                    read_zip(db,nested,name+'!'+i.filename,counts,pairs,progress,depth+1)
            else:
                counts['ignored_members']+=1


def import_file(store,path,progress=lambda text:None):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>MAX_FILE:
        raise ValueError('File missing or above 512 MiB')
    digest=sha256(path)
    counts=Counter()
    pairs=set()
    with store.connect() as db:
        old=db.execute('SELECT report FROM imports WHERE hash=?',(digest,)).fetchone()
        if old:
            return {**json.loads(old[0]),'already_imported':True}
        db.execute('BEGIN IMMEDIATE')
        with path.open('rb') as f:
            if path.name.lower().endswith('.zip'):
                read_zip(db,f,path.name,counts,pairs,progress)
            elif path.name.lower().endswith(('.csv','.csv.gz')):
                read_table(db,f,path.name,counts,pairs,progress)
            else:
                raise ValueError('지원 형식: AOA ZIP, CSV, CSV.GZ')
        if counts['recognized_tables']==0 or counts['rows_processed']==0:
            raise ValueError('지원하는 주문 이벤트 또는 원시 OHLCV를 찾지 못했습니다. AOA_candle_analysis.zip / order_context.csv / AOA TradingView 이벤트 CSV를 선택하세요. 원본 BitMEX 대용량 실행 CSV의 직접 재정산은 이 버전에서 하지 않습니다.')
        rebuild(db,pairs,progress)
        report=dict(counts,sha256=digest,filename=path.name,pairs=sorted(pairs),
            classification_policy='Imported labels are retrospective; context-only rows remain INCREASE/REDUCE without unsupported TP/STOP guesses.',
            integrity='Local SHA256 + archive CRC + row validation. Not proof of exchange provenance.')
        db.execute('INSERT INTO imports(hash,name,report) VALUES(?,?,?)',(digest,path.name,json.dumps(report,ensure_ascii=False)))
    return report
