"""Exact, checked integration edits; never run by the application launcher."""
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def replace(path,old,new,count=1):
    p=ROOT/path;s=p.read_text(encoding='utf-8')
    if new in s:return
    assert s.count(old)==count,(path,'unexpected source',s.count(old),old[:80])
    p.write_text(s.replace(old,new),encoding='utf-8')

p=ROOT/'aoa/seed.py';s=p.read_text(encoding='utf-8')
if "VERSION='seed-1'" in s:
    s=s.replace("VERSION='seed-1'", "VERSION='seed-2-daily'")
    s=s.replace('from .performance_ledger import PnlStore,finite,same', 'from .performance_ledger import PnlStore,finite,same\nfrom .wallet_daily import DAILY_SCHEMA, DailyBook, parse_stamp, parse_snapshot')
    start=s.index('def parse_stamp(text):');end=s.index('def order_value(e):')
    book='''class SeedBook:
    def __init__(self,rows=(),blocks=(),daily=()):
        self.rows=[dict(r) for r in rows];self.blocks=[dict(b) for b in blocks]
        self.daily=DailyBook(daily)
        self.has_data=bool(self.rows or self.blocks or self.daily.rows)
        self.accounts={r['account'] for r in self.rows}|{b['account'] for b in self.blocks}|self.daily.accounts
        self.by_kind={};self.times={}
        for kind in ('equity','wallet'):
            grouped=defaultdict(list)
            for r in self.rows:
                if r.get(kind+'_btc') is not None:grouped[r['t']].append(r)
            result=[]
            for t,rr in sorted(grouped.items()):
                values=[r[kind+'_btc'] for r in rr];conflict=not all(same(values[0],v) for v in values)
                result.append({'time_us':t,'btc':None if conflict else values[0],'conflict':conflict,'sources':sorted({r['source'] for r in rr}),'source_quality':sorted({r['quality'] for r in rr})})
            self.by_kind[kind]=result;self.times[kind]=[r['time_us'] for r in result]
    def at(self,t,kind=None):
        result={'btc':None,'kind':kind,'time_us':None,'age_seconds':None,'quality':'unavailable','reason':'잔고 자료를 연결하세요.','sources':[],'has_data':self.has_data}
        if len(self.accounts)>1:
            result['reason']='서로 다른 계좌의 잔고가 섞여 있습니다. 합산하거나 임의 계좌를 선택하지 않습니다.';return result
        for k in ((kind,) if kind else ('equity','wallet')):
            i=bisect.bisect_left(self.times[k],t)-1
            # Keep day-level and true timestamp observations separate. A day boundary
            # is availability metadata, NOT an invented transaction timestamp.
            daily=self.daily.at(t,self.blocks) if k=='wallet' and self.daily.rows else None
            if daily and daily.get('available_from_us') is not None:
                if i<0 or daily['available_from_us']>self.by_kind[k][i]['time_us']:
                    daily['has_data']=True
                    return daily
            if i<0:
                if daily:result.update(daily,has_data=True)
                continue
            point=self.by_kind[k][i];result.update(point,kind=k,age_seconds=(t-point['time_us'])/1e6)
            if point['conflict']:
                result.update(btc=None,reason='동일 시각 잔고값 충돌. 이전 잔고로 우회하지 않습니다.');return result
            if t-point['time_us']>MAX_AGE_US:
                result.update(btc=None,reason='직전 잔고가 36시간보다 오래되어 주문 시드 계산을 보류합니다.');return result
            if any(b['day']<=t//DAY_US and (b['day']+1)*DAY_US>point['time_us'] for b in self.blocks):
                result.update(btc=None,reason='시각 불명 잔고/입출금 이후 확정 시각 잔고가 아직 없습니다.');return result
            if not finite(point['btc']) or point['btc']<=0:
                result.update(btc=None,reason='양수 시드가 확인되지 않습니다.');return result
            result.update(quality='historical_reference',reason=('명시적 순자산 관측값을 주문 직전까지 유지한 참고값' if k=='equity' else '지갑잔고 관측값 기준 참고. 미실현손익 제외; 순자산/투입 증거금이 아님'))
            return result
        if self.has_data and result['reason']=='잔고 자료를 연결하세요.':
            result['reason']='잔고 자료는 연결됐지만 주문보다 앞선 사용 가능한 기준이 없습니다.'
        return result

'''
    s=s[:start]+book+s[end:]
    s=s.replace("PRIMARY KEY(digest,parser));\n'''", "PRIMARY KEY(digest,parser));\n''' + DAILY_SCHEMA")
    s=s.replace("rows=db.execute('SELECT * FROM seed_snapshots').fetchall();blocks=db.execute('SELECT * FROM seed_blocks').fetchall()", "rows=db.execute('SELECT * FROM seed_snapshots').fetchall();blocks=db.execute('SELECT * FROM seed_blocks').fetchall();daily=db.execute('SELECT * FROM seed_daily_rows').fetchall()")
    s=s.replace('self._seed_book=SeedBook(rows,blocks)', 'self._seed_book=SeedBook(rows,blocks,daily)')
    s=s.replace("'최초 진입 미확인','sources':[]}", "'최초 진입 미확인','sources':[],'has_data':self.seed_book().has_data}")
    s=s.replace("'관측 최초 주문 이전 보유량 존재/첫 끝점 미확인. 최초 시드로 단정하지 않음','sources':[]}", "'관측 최초 주문 이전 보유량 존재/첫 끝점 미확인. 최초 시드로 단정하지 않음','sources':[],'has_data':self.seed_book().has_data}")
    s=s.replace("r['seed_kind']=s.get('kind') if s else None", "r['seed_kind']=s.get('kind') if s else None\n            r['seed_basis']=s.get('basis') if s else None")
    s=s.replace("        return s\n", "        return s\n",1)
    old="            s['seed_ambiguous_days']=db.execute('SELECT COUNT(DISTINCT day) FROM seed_blocks').fetchone()[0]\n        return s"
    new="            s['seed_ambiguous_days']=db.execute('SELECT COUNT(DISTINCT day) FROM seed_blocks').fetchone()[0]\n        book=self.seed_book()\n        s['seed_daily_rows']=len(book.daily.rows)\n        s['seed_daily_days']=len(book.daily.points)\n        s['seed_daily_verified_days']=sum(p['valid'] for p in book.daily.points)\n        s['seed_data_connected']=book.has_data\n        return s"
    assert old in s;s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')

for name in ('aoa/version.py','web/index.html','web/boot.mjs','web/study-ui.mjs'):
    p=ROOT/name;s=p.read_text(encoding='utf-8')
    assert '0.4.0' in s or '0.4.1' in s,name
    p.write_text(s.replace('0.4.0','0.4.1'),encoding='utf-8')
replace('web/app.mjs', "`v${d.version} · 주문 ${d.orders.toLocaleString()}건`", "`v${d.version} · 주문 ${d.orders.toLocaleString()}건 · 잔고 ${d.seed_daily_verified_days?'일별 '+d.seed_daily_verified_days+'일(참고)':d.seed_snapshots?d.seed_snapshots+'건':d.seed_data_connected?'검산 보류':'미연결'}`")
replace('web/app.mjs', "'초기 시드 '+seedReturnText(ep)", "(ep.seed_basis==='prior_day_ledger_close'?'초기 전일잔고 ':'초기 시드 ')+seedReturnText(ep)")
replace('web/pnl-ui.mjs', " root.append(seedBox);", " if(p.seed_initial?.basis==='prior_day_ledger_close')seedBox.append(el('p',p.seed_initial.reason,'warning'));\n root.append(seedBox);")
p=ROOT/'README.md';s=p.read_text(encoding='utf-8')
if 'v0.4.1 잔고 형식 수정' not in s:
    p.write_text('# v0.4.1 잔고 형식 수정\n\n잘린 timestamp 때문에 시드가 미연결되던 문제를 수정했습니다. 새 폴더에서 실행 후 기존 wallet CSV를 한 번 다시 선택하세요. 원본 날짜와 금액·잔고 연결을 검산하여 이전 기록일 마감 잔고를 참고값으로 사용합니다. 정확한 주문 직전 시드로 표시하지 않습니다. 자세한 사용법: [v0.4.1 안내](docs/RELEASE_v0.4.1.md).\n\n'+s,encoding='utf-8')
print('WALLET_V041_INTEGRATED')
