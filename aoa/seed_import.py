"""Import wallet snapshots AND date-only ledgers without inventing intraday time."""
from __future__ import annotations
import csv
import gzip
import io
import json
import re
import zipfile
from collections import Counter
from pathlib import Path
from .seed import SCHEMA, VERSION, recognizes, parse_snapshot
from .wallet_daily import DailyBook, norm, field, resolve_time, DAY_US
from .importer import sha256, safe_members, BoundedReader
from .performance_import import import_file as import_performance


def import_file(store, path, display_name=None, progress=lambda _:None):
    path=Path(path);name=display_name or path.name;digest=sha256(path)
    with store.connect() as db:
        db.executescript(SCHEMA)
        prior=db.execute('SELECT report FROM seed_imports WHERE digest=? AND parser=?',(digest,VERSION)).fetchone()
    seed_report=json.loads(prior[0]) if prior else None
    counts=Counter();headers_seen=[];budget=[0];other_data=False
    if not prior and not name.lower().endswith('.xlsx'):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Reparse SAME bytes with the new parser. Clear this digest only, atomically.
            pattern=digest[:12]+'/%'
            for table in ('seed_snapshots','seed_blocks','seed_daily_rows'):
                db.execute('DELETE FROM '+table+' WHERE source LIKE ?',(pattern,))
            db.execute("DELETE FROM issues WHERE source LIKE ? AND reason LIKE '시드 연결:%'",(pattern,))
            def reject(source, line, raw, exc):
                counts['rejected_rows']+=1
                if counts['rejected_rows']<=500:
                    db.execute('INSERT INTO issues(source,line,reason) VALUES(?,?,?)',(source,line,'시드 연결: '+str(exc)[:350]))
                # A rejected known-day balance must not silently bridge a ledger gap.
                try:
                    r={norm(k):v for k,v in raw.items() if k is not None}
                    t,precision,_=resolve_time(r)
                    account=field(r,'account','accountid','accountkey') or 'default'
                    db.execute('INSERT OR REPLACE INTO seed_blocks VALUES(?,?,?,?)',(source,t//DAY_US,account,'잔고 행 검증 거부: '+str(exc)[:200]))
                except (ValueError,TypeError,OverflowError):
                    pass
            def parse(stream, source):
                nonlocal other_data
                with io.TextIOWrapper(io.BufferedReader(BoundedReader(stream,budget)),encoding='utf-8-sig',newline='') as text:
                    reader=csv.DictReader(text);headers=reader.fieldnames or []
                    if not recognizes(headers):
                        if re.search(r'(wallet|equity|잔고|시드)',source,re.I):headers_seen.append({'source':source,'headers':headers[:30]})
                        if any(h in headers for h in ('orderid','source_orderid','ep_id','open','net_pnl_btc','최종 순손익(BTC)')):other_data=True
                        return
                    counts['seed_files']+=1
                    src=digest[:12]+'/'+source
                    for n,raw in enumerate(reader,2):
                        counts['total_rows']+=1
                        if not any(str(v or '').strip() for v in raw.values()):
                            counts['blank_rows']+=1
                            continue
                        try:
                            row=parse_snapshot(raw)
                            if row is None:
                                counts['ignored_rows']+=1
                                continue
                            if 'daily' in row:
                                values=(row['daily'],row['wallet_btc'],row['amount_btc'],row['account'],row['kind'])
                                existing=db.execute('SELECT day,wallet_btc,amount_btc,account,kind FROM seed_daily_rows WHERE source=? AND row_key=?',(src,row['row_key'])).fetchone()
                                if existing is not None and tuple(existing)!=values:
                                    raise ValueError('동일 일별 잔고 ID의 값이 충돌합니다.')
                                db.execute('INSERT OR IGNORE INTO seed_daily_rows VALUES(?,?,?,?,?,?,?,?,?)',(src,row['row_key'],*values,n,row['quality']))
                                counts['daily_duplicate_rows' if existing else 'daily_rows']+=1
                            if 'block' in row:
                                db.execute('INSERT OR REPLACE INTO seed_blocks VALUES(?,?,?,?)',(src,row['block'],row['account'],row['reason']))
                                counts['ambiguous_rows']+=1
                            elif 'daily' not in row:
                                values=(row['t'],row['wallet_btc'],row['equity_btc'],row['account'])
                                existing=db.execute('SELECT t,wallet_btc,equity_btc,account FROM seed_snapshots WHERE source=? AND row_key=?',(src,row['row_key'])).fetchone()
                                if existing is not None and tuple(existing)!=values:
                                    raise ValueError('동일 잔고 ID의 값이 충돌합니다.')
                                db.execute('INSERT OR IGNORE INTO seed_snapshots VALUES(?,?,?,?,?,?,?,?)',(src,row['row_key'],*values,row['precision'],row['quality']))
                                counts['snapshot_rows']+=1
                        except (ValueError,KeyError,TypeError,OverflowError) as exc:
                            reject(src,n,raw,exc)
                        if n%1000==0:
                            progress({'message':'잔고 날짜·단위·일별 연결 검산: '+source,'counts':dict(counts)})
            def walk(stream, source, depth=0):
                nonlocal other_data
                if depth>2:raise ValueError('잔고 ZIP 중첩 깊이 초과')
                if source.lower().endswith('.zip'):
                    with zipfile.ZipFile(stream) as z:
                        for member in safe_members(z):
                            if member.is_dir():continue
                            child=source+'/'+member.filename;low=member.filename.lower()
                            if 'execution-' in low:continue
                            if low.endswith(('.csv','.csv.gz')):
                                with z.open(member) as f:
                                    if low.endswith('.gz'):
                                        with gzip.GzipFile(fileobj=f) as g:parse(g,child)
                                    else:parse(f,child)
                            elif low.endswith('.zip') and re.search(r'(wallet|seed|equity|잔고)',low):
                                if member.file_size>128*1024**2:raise ValueError('중첩 잔고 ZIP 크기 제한')
                                with z.open(member) as f:walk(io.BytesIO(f.read()),child,depth+1)
                            elif low.endswith('.xlsx'):other_data=True
                elif source.lower().endswith('.gz'):
                    with gzip.GzipFile(fileobj=stream) as f:parse(f,source)
                else:parse(stream,source)
            with path.open('rb') as f:walk(f,name)
            if counts['seed_files']:
                daily=DailyBook(db.execute('SELECT * FROM seed_daily_rows WHERE source LIKE ?',(pattern,)).fetchall())
                counts['daily_days']=len(daily.points)
                counts['daily_verified_days']=sum(p['valid'] for p in daily.points)
                counts['daily_conflict_days']=counts['daily_days']-counts['daily_verified_days']
                state='connected' if counts['snapshot_rows'] else 'connected_daily_reference' if counts['daily_verified_days'] else 'connected_but_unusable'
                seed_report={'name':name,'counts':dict(counts),'parser':VERSION,'sha256':digest,'state':state,
                             'note':'잘린 시각은 복원하지 않음. 일별 잔고는 다음 날짜부터 이전 기록일 참고로 사용. 당일 입출금 시각 불명은 보류. 지갑잔고와 순자산/증거금 구분.'}
                db.execute('INSERT OR REPLACE INTO seed_imports VALUES(?,?,?)',(digest,VERSION,json.dumps(seed_report,ensure_ascii=False)))
                db.commit()
            else:db.rollback()
    base={}
    if not seed_report or other_data:
        try:base=import_performance(store,path,name,progress)
        except ValueError as exc:
            if not seed_report:raise
            if not any(x in str(exc) for x in ('지원되는 데이터가 없습니다','연결 가능한 손익 자료가 없습니다')):raise
    if seed_report:
        report={'name':name,'seed_import':seed_report,'other_import':base,'already_imported':bool(prior)}
        with store.connect() as db:
            db.execute('INSERT INTO imports(sha256,name,report) VALUES(?,?,?) ON CONFLICT(sha256) DO UPDATE SET report=excluded.report',(digest,name,json.dumps(report,ensure_ascii=False)))
        if hasattr(store,'invalidate_seed'):store.invalidate_seed()
        c=seed_report['counts']
        message=f"잔고 연결: 시각 자료 {c.get('snapshot_rows',0)}건 / 일별 참고 {c.get('daily_verified_days',0)}일 / 거부 {c.get('rejected_rows',0)}행"
        if seed_report.get('state')=='connected_but_unusable':message+=' · 사용할 잔고 없음: 검증 기록 확인'
        progress({'message':message,'counts':c})
        return report
    return base
