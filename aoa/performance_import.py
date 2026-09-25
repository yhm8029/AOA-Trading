"""Add position PNL ledgers to the existing importer without deleting old data.

Old uploads skipped episodes.csv. A versioned second pass rereads those sources,
including the same ZIP SHA, while the old importer reuses already imported candles.
XLSX is read with stdlib only. Cached values only: no formulas/macros/external links.
"""
from __future__ import annotations
import csv
import gzip
import io
import json
import re
import zipfile
from collections import Counter
from datetime import datetime,timedelta
from pathlib import Path,PurePosixPath
import xml.etree.ElementTree as ET
from .importer import import_file as import_market, sha256, safe_members, BoundedReader, csv_kind
from .model import adapt_order,number,pick
from .store import Store
from .performance_ledger import LEDGER_SCHEMA,PARSER_VERSION,ALIASES,is_summary,put_summary,tidy

NS={'x':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def _xml(z,name):
    i=z.getinfo(name)
    if i.file_size>64*1024*1024:raise ValueError('XLSX XML 크기 제한 초과')
    raw=z.read(name)
    if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:raise ValueError('XLSX XML DTD/entity 불허')
    return ET.fromstring(raw)

def xlsx_tables(z):
    safe_members(z)
    strings=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        root=_xml(z,'xl/sharedStrings.xml')
        strings=[''.join(t.text or '' for t in s.iter('{'+NS['x']+'}t')) for s in root]
    workbook=_xml(z,'xl/workbook.xml');pr=workbook.find('x:workbookPr',NS)
    epoch=datetime(1904,1,1) if pr is not None and pr.get('date1904','').lower() in {'1','true'} else datetime(1899,12,30)
    date_headers=set(ALIASES['start']+ALIASES['end'])
    for name in sorted(z.namelist()):
        if not re.fullmatch(r'xl/worksheets/sheet\d+\.xml',name):continue
        root=_xml(z,name);headers=None;data=[]
        for rownum,row in enumerate(root.findall('x:sheetData/x:row',NS)):
            cells={}
            for c in row:
                ref=c.get('r','');letters=re.sub('[^A-Z]','',ref);idx=0
                for letter in letters:idx=idx*26+ord(letter)-64
                if idx<1 or idx>256:continue
                v=c.find('x:v',NS);v=v.text if v is not None else None
                kind=c.get('t')
                if kind=='s' and v is not None:v=strings[int(v)]
                elif kind=='inlineStr':v=''.join(t.text or '' for t in c.findall('.//x:t',NS))
                elif kind=='e':v=None
                cells[idx-1]=v
            if headers is None:
                if rownum>100:break
                candidate=[str(cells.get(i) or '').strip() for i in range(max(cells,default=-1)+1)]
                if is_summary(candidate):headers=candidate
                continue
            if not cells:continue
            mapped={h:cells.get(i) for i,h in enumerate(headers) if h}
            for k in date_headers.intersection(mapped):
                v=mapped[k]
                if v is not None:
                    try:
                        n=float(v)
                        if 0<n<100000:mapped[k]=(epoch+timedelta(days=n)).isoformat()
                    except (ValueError,OverflowError):pass
            data.append(mapped)
        if headers is not None:yield name,data

def import_file(store,path,display_name=None,progress=lambda _:None):
    path=Path(path);name=display_name or path.name;digest=sha256(path)
    with store.connect() as db:
        db.executescript(LEDGER_SCHEMA)
        prior=db.execute('SELECT report FROM performance_imports WHERE digest=? AND parser_version=?',(digest,PARSER_VERSION)).fetchone()
    # The ordinary importer still handles candles, endpoints and CSV feature history.
    base={}
    if not name.lower().endswith('.xlsx'):
        try:base=import_market(store,path,name,progress)
        except ValueError as exc:
            if '지원되는 데이터가 없습니다' not in str(exc):raise
    if prior:
        report=json.loads(prior[0]);report['already_imported']=True;report['market_import']=base;return report
    counts=Counter();skipped=[];budget=[0]
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        def rejected(source,line,exc):
            counts['performance_rejected_rows']+=1
            if counts['performance_rejected_rows']<=1000:
                db.execute('INSERT INTO issues(source,line,reason) VALUES(?,?,?)',(source,line,'손익 연결: '+str(exc)[:350]))
        def parse_rows(rows,source):
            for n,row in enumerate(rows,1):
                row=tidy(row)
                try:
                    if is_summary(row):
                        put_summary(db,row,digest[:12]+'/'+source);counts['position_summaries']+=1
                    elif csv_kind(row)=='orders':
                        if not row.get('qty') and row.get('order_group_qty_audit_only'):row['qty']=row['order_group_qty_audit_only']
                        o=adapt_order(row)
                        # Only explicitly BTC-valued columns are accepted; generic cost is ambiguous.
                        val=number(pick(row,'contract_value_btc','order_value_btc','notional_btc'))
                        if val is not None:
                            if val<=0:raise ValueError('BTC 계약가치는 양수여야 합니다.')
                            o['contract_value_btc']=val
                        if 'inverse_price' in row and not o.get('inverse_price'):
                            o['inverse_price']=number(row['inverse_price'])
                        Store.order(db,o,source);counts['performance_orders']+=1
                except (ValueError,KeyError,TypeError,OverflowError) as exc:rejected(source,n,exc)
                if n%2000==0:progress({'message':'손익 자료 연결: '+source,'counts':dict(counts)})
        def parse_csv(stream,source):
            with io.TextIOWrapper(io.BufferedReader(BoundedReader(stream,budget)),encoding='utf-8-sig',newline='') as text:
                reader=csv.DictReader(text);h=[str(k).strip() for k in reader.fieldnames or []]
                if is_summary(h) or csv_kind(h)=='orders':
                    # Large pre/post feature files do not add a net-PNL denominator.
                    if 'pre_1m_body_pct' in h or 'pre_return_5m_pct' in h:return
                    parse_rows(reader,source)
                elif re.search(r'(episode|position|포지션)',source,re.I):
                    skipped.append({'source':source,'headers':h[:40],'reason':'명시적 BTC 손익 열 미확인; 검증 기록 참고'})
        def walk(stream,source,depth=0):
            if depth>3:raise ValueError('중첩 ZIP 깊이 초과')
            if source.lower().endswith(('.zip','.xlsx')):
                with zipfile.ZipFile(stream) as z:
                    members=safe_members(z)
                    if 'xl/workbook.xml' in z.namelist():
                        for sheet,rows in xlsx_tables(z):parse_rows(rows,source+'/'+sheet)
                        return
                    for i in members:
                        child=source+'/'+i.filename;suffix=i.filename.lower()
                        if i.is_dir():continue
                        if suffix.endswith(('.csv','.csv.gz')):
                            with z.open(i) as f:
                                if suffix.endswith('.gz'):
                                    with gzip.GzipFile(fileobj=f) as g:parse_csv(g,child)
                                else:parse_csv(f,child)
                        elif suffix.endswith(('.zip','.xlsx')) and not re.search(r'-1m-\d{4}',suffix):
                            if i.file_size>128*1024*1024:raise ValueError('중첩 손익 ZIP 128MB 초과')
                            with z.open(i) as f:walk(io.BytesIO(f.read()),child,depth+1)
            elif source.lower().endswith('.gz'):
                with gzip.GzipFile(fileobj=stream) as f:parse_csv(f,source)
            else:parse_csv(stream,source)
        with path.open('rb') as f:walk(f,name)
        if not base and not counts['position_summaries'] and not counts['performance_orders']:
            raise ValueError('연결 가능한 손익 자료가 없습니다. AOA 거래분석 XLSX의 포지션 시트 / 명시적 net_pnl_btc가 있는 episodes.csv / 기존 TradingView events.csv를 선택하세요. 수식 셀은 계산된 저장값이 필요합니다. 확인 열: '+str(skipped[:2]))
        report={'name':name,'sha256':digest,'parser_version':PARSER_VERSION,'counts':dict(counts),'market_import':base,'unrecognized_performance_members':skipped[:40],
                'note':'구버전이 건너뛴 손익표도 재연결. 이미 적재된 봉 재중복 없음. 수수료/펀딩은 보고값, 단위 추정 없음.'}
        db.execute('INSERT OR REPLACE INTO performance_imports VALUES(?,?,?)',(digest,PARSER_VERSION,json.dumps(report,ensure_ascii=False)))
        # Surface performance-only imports in the existing audit panel as well.
        db.execute('INSERT INTO imports(sha256,name,report) VALUES(?,?,?) ON CONFLICT(sha256) DO UPDATE SET report=excluded.report',
                   (digest,name,json.dumps(report,ensure_ascii=False)))
        db.commit();return report
