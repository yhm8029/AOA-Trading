"""Evidence-linked trade commentary. Deterministic research hypotheses, not mind reading.

Only candles CLOSED before the first fill enter a rationale. Subsequent PNL,
last-fill features and future maximum exposure never enter candidate selection.
No network calls, LLM keys or user-data uploads are involved.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import datetime, timezone
from .review import ReviewStore, finite
from .model import time_us

ENGINE_VERSION = '0.3.0'
HORIZONS = (1, 5, 15, 60, 240, 1440)
METHODS = ('trend_continuation', 'pullback', 'countertrend', 'mean_reversion',
           'exhaustion', 'failed_breakout', 'momentum', 'range_extreme',
           'bounce_reload', 'breakout_continuation')


def num(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def pct(v):
    return '미확보' if v is None else f'{v:+.3f}%'


def amount(v):
    return '미확보' if v is None else f'{v:,.0f}'


def stamp(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat()


def closed_context(rows, first_us):
    """rows=(t,o,h,l,c,v), unique validated UTC 1m bars; no forward fill.

    Return h is last completed close / close h minutes earlier - 1.
    Structure is successive block highs/lows, NOT future-confirmed pivots.
    """
    end = int(first_us) // 60_000_000 * 60
    points = {int(r[0]): tuple(r) for r in rows if int(r[0])+60 <= end}
    def segment(n, finish=end):
        out = [points.get(t) for t in range(finish-n*60, finish, 60)]
        return out if out and all(x is not None for x in out) else None
    frames = []
    for h in HORIZONS:
        part, retpart = segment(h), segment(h+1)
        previous = segment(h, end-h*60)
        v = {'minutes':h, 'start':end-h*60, 'end':end, 'source':'local_closed_1m',
             'available':part is not None, 'return_pct':None, 'range_location_pct':None,
             'volume':None, 'volume_ratio':None, 'high':None, 'low':None, 'structure':'미확보'}
        if retpart:
            v['return_pct'] = (retpart[-1][4]/retpart[0][4]-1)*100
        if part:
            lo, hi = min(r[3] for r in part), max(r[2] for r in part)
            v.update(high=hi, low=lo, volume=sum(r[5] for r in part),
                     range_location_pct=100*(part[-1][4]-lo)/(hi-lo) if hi>lo else None)
            if previous and sum(r[5] for r in previous)>0:
                v['volume_ratio'] = v['volume']/sum(r[5] for r in previous)
            if h>=15:
                # Three already completed, consecutive equal-size blocks.
                size=h//3
                blocks=[part[i*size:(i+1)*size] for i in range(3)]
                highs=[max(r[2] for r in b) for b in blocks]
                lows=[min(r[3] for r in b) for b in blocks]
                v['structure']='상승 구조' if highs[0]<highs[1]<highs[2] and lows[0]<lows[1]<lows[2] else '하락 구조' if highs[0]>highs[1]>highs[2] and lows[0]>lows[1]>lows[2] else '혼합/횡보'
        frames.append(v)
    last=segment(1); base=segment(20,end-60)
    candle=None
    if last:
        t,o,h,l,c,v=last[0]; width=h-l
        candle={'time':t,'open':o,'high':h,'low':l,'close':c,'volume':v,
                'body_return_pct':(c/o-1)*100,
                'close_location_pct':100*(c-l)/width if width else None,
                'upper_wick_pct':100*(h-max(o,c))/width if width else None,
                'lower_wick_pct':100*(min(o,c)-l)/width if width else None,
                'relative_volume20':None,'range_expansion20':None,
                'sweep_low20':None,'sweep_high20':None,'break_up20':None,'break_down20':None}
        if base:
            average=sum(r[5] for r in base)/20
            spread=sum(r[2]-r[3] for r in base)/20
            low20=min(r[3] for r in base);high20=max(r[2] for r in base)
            candle.update(relative_volume20=v/average if average>0 else None,
                          range_expansion20=width/spread if spread>0 else None,
                          sweep_low20=l<low20 and c>low20,
                          sweep_high20=h>high20 and c<high20,
                          break_up20=c>high20,break_down20=c<low20)
    return {'end':end,'frames':frames,'last_candle':candle,
            'valid_1m':sum(end-1440*60<=t<end for t in points),
            'expected_1m':1440,'source':'local_closed_1m'}


def with_imported_context(context, event):
    """Fallback only to explicitly timestamped FIRST-endpoint pre_* columns.

    The fields are labelled supplied, not recalculated. Never consume post_* or
    last endpoint features. A stale imported snapshot is ignored.
    """
    f={**event.get('context',{}),**event.get('features',{})}
    try:
        matched=time_us(f.get('pre_last_open_utc'))//1_000_000==context['end']-60
    except (ValueError, TypeError):
        matched=False
    if not matched or event.get('first_observed') is False:
        return context
    for frame in context['frames']:
        if frame['available']:
            continue
        h=frame['minutes']
        ret=num(f.get(f'pre_return_{h}m_pct'))
        loc=num(f.get(f'pre_range_location_{h}m_pct'))
        if ret is not None or loc is not None:
            frame.update(return_pct=ret,range_location_pct=loc,source='supplied_first_endpoint_pre_features',structure='未검산 제공값',available=False)
    if context['last_candle'] is None and all(num(f.get('pre_1m_'+k)) is not None for k in ('open','high','low','close','volume')):
        c={k:num(f.get('pre_1m_'+k)) for k in ('open','high','low','close','volume')}
        if not 0<c['low']<=min(c['open'],c['close'])<=max(c['open'],c['close'])<=c['high'] or c['volume']<0:
            return context
        c.update(time=context['end']-60,source='supplied_first_endpoint_pre_features',
                 body_return_pct=(c['close']/c['open']-1)*100,
                 close_location_pct=num(f.get('pre_1m_close_location_pct')),
                 upper_wick_pct=num(f.get('pre_1m_upper_wick_pct')),
                 lower_wick_pct=num(f.get('pre_1m_lower_wick_pct')),
                 relative_volume20=num(f.get('pre_volume_1m_vs_prior_20m')),
                 range_expansion20=num(f.get('pre_range_expansion_vs_prior20')),
                 sweep_low20=num(f.get('pre_sweep_reclaim_low_prior20'))==1,
                 sweep_high20=num(f.get('pre_sweep_reclaim_high_prior20'))==1,
                 break_up20=None,break_down20=None)
        context['last_candle']=c
    return context


def explain_event(event, prior, context, cutoff=None):
    """All prior order references must have completed BEFORE this first fill.

    Current order final quantity/after-position are retrospective and only shown
    once its recorded last fill has passed cutoff. They are never candidate inputs
    in a partial-order replay. Confidence is evidence strength, NOT win probability.
    """
    t=int(event['first_us']);direction=event.get('direction')
    sign=1 if direction=='Long' else -1 if direction=='Short' else 0
    is_entry=event.get('role')=='Entry'
    observed=event.get('first_observed',True)
    px=num(event.get('first_price')) if observed else None
    before=num(event.get('position_before')) if observed else None
    basis=num(event.get('basis_before')) if observed else None
    completed=cutoff is None or event.get('last_observed') and event.get('last_us',t)<cutoff*1_000_000
    qty=num(event.get('qty')) if completed else None
    after=num(event.get('position_after')) if completed else None
    move=sign*(px/basis-1)*100 if sign and px and basis and basis>0 else None
    if is_entry:
        action='ENTRY' if before==0 else 'ADD' if before is not None else 'INCREASE'
    elif 'stop' in str(event.get('order_type') or '').lower(): action='STOP'
    elif after==0 and event.get('last_observed'): action='CLOSE'
    elif move is not None and move>0: action='TP'
    elif move is not None and move<0: action='LOSS_REDUCE'
    else: action='REDUCE'
    labels={'ENTRY':'최초 진입','ADD':'추가','INCREASE':'진입/추가','STOP':'스톱 주문','CLOSE':'전량 종료','TP':'이익 방향 감량','LOSS_REDUCE':'손실 방향 감량','REDUCE':'감량'}
    facts=[];candidates=[];contradictions=[];limitations=[]
    def fact(text,start=None,end=None,source='order_record',tf='1m'):
        item={'text':text,'source':source}
        if start is not None:item.update(start=start,end=end if end is not None else start+60,tf=tf)
        facts.append(item)
    def candidate(code,title,why,evidence,counter):
        candidates.append({'code':code,'title':title,'interpretation':why,'evidence':evidence,'counter_evidence':counter,'status':'연구 가설 · 본인 의도 미확인'})
    fact(f"첫 관측 체결 {stamp(t/1_000_000)} · {direction or '방향 미확보'} · {labels[action]}.")
    if px is not None:fact(f'BitMEX 첫 체결가 {px:,.8g}. 시장 캔들의 가격과 별도입니다.')
    if before is not None:fact(f'주문 첫 체결 직전 보유 {amount(before)} 계약.')
    if completed:
        fact(f'관측 주문 전체 수량 {amount(qty)} 계약 · 마지막 체결 뒤 보유 {amount(after)} 계약. 주문 전체가 끝난 뒤의 집계값입니다.')
    else:limitations.append('복기 시각에 이 주문의 분할체결이 끝났는지 확인되지 않아 최종 수량·평균가격·종료 후 보유량은 숨겼습니다.')
    if move is not None:
        fact(f'첫 체결가와 직전 평균단가 {basis:,.8g} 비교: 방향환산 {pct(move)}. 수수료·펀딩·레버리지 미반영 가격 차이입니다.')
    if not observed:limitations.append('첫 체결 끝점 미확보: 이 시각을 실제 최초 진입으로 확정할 수 없습니다.')
    if before is None:limitations.append('주문 직전 보유량 미확보: 신규 진입과 추가진입을 확정 구분하지 않습니다.')
    frames={f['minutes']:f for f in context['frames']}
    for h in (5,60,240,1440):
        f=frames[h]
        if f['return_pct'] is not None:
            fact(f"직전 {h}분 가격 변화 {pct(f['return_pct'])} · 범위 내 위치 {f['range_location_pct']:.1f}%." if f['range_location_pct'] is not None else f"직전 {h}분 가격 변화 {pct(f['return_pct'])}.",f['start'],f['end'],f['source'],'1h' if h>=240 else '5m' if h>=60 else '1m')
    c=context['last_candle'] or {};rv=c.get('relative_volume20');wick=c.get('lower_wick_pct' if sign==1 else 'upper_wick_pct')
    if c:
        fact(f"직전 완성 1분봉: 시가→종가 {pct(c.get('body_return_pct'))}, 거래량 {amount(c.get('volume'))}, 이전 20분 평균 대비 {rv:.2f}배." if rv is not None else f"직전 완성 1분봉: 시가→종가 {pct(c.get('body_return_pct'))}, 거래량 {amount(c.get('volume'))}. 상대거래량 분모 미확보.",c['time'],c['time']+60,c.get('source','local_closed_1m'))
    r5=frames[5]['return_pct'];r60=frames[60]['return_pct'];r240=frames[240]['return_pct']
    loc=frames[60]['range_location_pct'];structure=frames[240]['structure']
    directional5=sign*r5 if sign and r5 is not None else None
    directional240=sign*r240 if sign and r240 is not None else None
    favorable_loc=loc if sign==1 else 100-loc if sign and loc is not None else None
    aligned_structure=structure==('상승 구조' if sign==1 else '하락 구조') if sign else False
    opposed_structure=structure==('하락 구조' if sign==1 else '상승 구조') if sign else False
    if opposed_structure:
        contradictions.append(f'직전 4시간은 {structure}로 현재 포지션과 반대입니다. 단순 추세추종으로 설명하기 어렵습니다.')
    if rv is not None and rv<1:
        contradictions.append(f'직전 상대거래량은 {rv:.2f}배로 평균 미만입니다. 거래량 폭발을 이유로 붙일 근거가 없습니다.')
    if directional240 is not None and directional240<0:
        contradictions.append(f'4시간 방향환산 변화 {pct(directional240)}: 큰 범위도 불리한 방향입니다. 단기 반등 기대와 추세 전환 확인을 구분해야 합니다.')
    previous=[e for e in prior if e.get('first_us',t)<t and e.get('last_observed') and e.get('last_us',t)<t]
    previous.sort(key=lambda e:e['last_us']);p=previous[-1] if previous else None
    if is_entry:
        if before is not None and before>0 and move is not None:
            text='불리한 방향에서 보유량을 늘린 추가' if move<0 else '유리한 방향으로 움직인 뒤 늘린 추가'
            fact(text+'입니다. 이것만으로 그 판단이 옳았다는 뜻은 아닙니다.')
        if sign and directional5 is not None and directional5<0 and aligned_structure and directional240 is not None and directional240>0:
            candidate('pullback','큰 흐름 안의 되돌림 진입/추가',f'4시간은 {structure}인데 직전 5분은 포지션 반대 방향 {pct(directional5)}입니다. 큰 방향을 유지하며 단기 조정을 받은 행동과 부합합니다.', ['4시간 구간별 고점·저점 구조','직전 5분 방향환산 변화'], '조정이 끝났다는 보장은 없습니다. 앞선 저점/고점 이탈이 계속되면 이 해석은 약해집니다.')
        swept=c.get('sweep_low20' if sign==1 else 'sweep_high20')
        if sign and swept:
            candidate('failed_breakout','직전 극값 이탈 후 복귀에 반응', '직전 완성 봉이 이전 20분의 극값을 잠시 넘었다가 범위 안으로 마감했습니다. 이탈 실패를 보고 반대 방향을 선택했을 가능성이 있습니다.', ['직전 봉 고가·저가·종가','그 이전 20분 극값'], '종가 복귀는 한 번의 반응일 뿐입니다. 이후 다시 이탈할 수 있으며 지정가가 그보다 먼저 제출됐을 수도 있습니다.')
        if sign and rv is not None and rv>=2 and wick is not None and wick>=35 and (swept or c.get('range_expansion20') is not None and c['range_expansion20']<1):
            candidate('exhaustion','큰 거래량 대비 가격 진행 둔화 후보',f'상대거래량 {rv:.2f}배와 반대 진행을 되돌린 꼬리 {wick:.1f}%가 함께 관측됩니다. 공격적인 물량이 나와도 가격이 잘 진행되지 않는다고 해석했을 가능성입니다.', ['직전 상대거래량','꼬리/범위·극값 복귀'], 'OHLCV만으로 실제 흡수·매수/매도 주체는 확인할 수 없습니다. 거래량 급증 자체는 수익 신호로 검증되지 않았습니다.')
        if sign and favorable_loc is not None and favorable_loc<=20 and directional5 is not None and directional5<0:
            candidate('mean_reversion','단기 범위 끝에서 반등/되돌림을 받은 진입',f'포지션 방향으로 환산한 1시간 범위 위치는 {favorable_loc:.1f}%이고, 직전 5분은 {pct(directional5)}로 역행했습니다. 이미 반전이 끝나서 추격했다기보다 범위 끝에서 반대 반응을 예상한 행동입니다.', ['1시간 범위 위치','5분 역행'], '범위 끝은 추세가 강할 때 계속 확장됩니다. 반전 확인 여부는 별도로 보아야 합니다.')
        broke=c.get('break_up20' if sign==1 else 'break_down20')
        if sign and broke and directional5 is not None and directional5>0:
            candidate('breakout_continuation','직전 범위 돌파 방향에 동참',f'직전 완성 봉 종가가 이전 20분 범위를 포지션 방향으로 벗어났고, 5분 변화도 {pct(directional5)}로 같은 방향입니다.', ['직전 종가/이전 20분 범위','5분 방향 일치'], '돌파 유지 여부는 아직 확정되지 않았습니다. 거래량 확대가 없거나 즉시 범위로 돌아오면 추격 실패 후보입니다.')
        if sign and aligned_structure and directional5 is not None and directional5>0 and not broke:
            candidate('trend_continuation','진행 중인 방향에 보유량 확대',f'4시간 {structure}와 5분 방향환산 {pct(directional5)}가 같은 방향입니다. 진행에 동참하는 행동과 부합하지만 특정 진입선까지 확정할 수는 없습니다.', ['완성 구간의 고저점 구조','단기 방향'], '평균단가 대비 유리한 추가가 항상 추세추종은 아닙니다. 포지션 전체의 앞선 운영과 함께 해석해야 합니다.')
        if p and p.get('role')=='Exit' and p.get('direction')==direction and t-p['last_us']<=6*3600*1_000_000:
            prior_px=num(p.get('last_price')) or (num(p.get('first_price')) if p.get('first_us')==p.get('last_us') else None)
            if sign and px and prior_px and sign*(px/prior_px-1)<0:
                candidate('bounce_reload','먼저 줄인 뒤 더 유리한 가격에서 재확대',f'직전 감량이 끝난 가격 {prior_px:,.8g}보다 이번 첫 체결가 {px:,.8g}가 재진입 관점에서 유리합니다. 일부 회수 후 되돌림에서 물량을 다시 얹는 흐름 후보입니다.', ['이전 완료 감량','현재 첫 체결가'], '다른 주문이 사이에 섞였거나 이전 최종체결가가 없으면 이 비교를 하지 않습니다. 의도나 추가분의 회계상 귀속은 확정하지 않습니다.')
        if not candidates and directional5 is not None and directional5<0:
            candidate('countertrend','직전 움직임과 반대로 진입/확대',f'직전 5분 방향환산 변화 {pct(directional5)}인데 노출을 늘렸습니다. 단기 역행을 받아 반응을 노린 설명은 가능하지만, 지지·저항 방어 근거는 충분하지 않습니다.', ['5분 역행','진입/추가 역할'], '반전 확인, 단순 평균단가 조정, 미리 걸어 둔 지정가 체결을 현재 자료만으로 구분하기 어렵습니다.')
    else:
        if move is not None and move>0:
            candidate('profit_harvest','평균단가보다 유리해진 가격에서 회수',f'첫 감량 가격이 직전 평균단가보다 방향상 {pct(move)} 유리합니다. 방향 예측을 완전히 바꾸지 않고 일부 수익 기회를 회수한 행동과 부합합니다.', ['BitMEX 첫 감량가','직전 평균단가'], '반대 신호 때문인지 목표가 도달 때문인지는 별도입니다. 이후 가격이 계속 유리하게 움직여도 이 감량이 당시 비합리적이었다고 단정할 수 없습니다.')
        elif move is not None and move<0:
            candidate('risk_reduce','평균단가보다 불리한 구간에서 위험 감소',f'첫 감량 가격이 직전 평균단가보다 방향상 {pct(move)} 불리합니다. 노출 축소는 확인되지만 이 한 주문으로 방향 가설 전체를 포기했다고 단정하지 않습니다.', ['첫 감량가/직전 평균단가','감량 역할'], '최근 추가분만 되돌렸을 수도 있습니다. 기존 보유량과 이후 남긴 물량을 확인해야 합니다.')
        if action=='STOP':
            candidate('recorded_stop','기록된 스톱 주문의 체결',f"원장 주문유형에 스톱이 기록돼 있습니다. 발동가격은 {amount(num(event.get('stop_trigger')))}입니다. 실제 체결가와 발동가는 다를 수 있습니다.",['원본 주문유형/발동가격'], '이 가격으로 스톱을 설정한 심리나 설정 시점은 체결 기록만으로 알 수 없습니다.')
        if completed and p and p.get('role')=='Entry' and p.get('direction')==direction and t-p['last_us']<=6*3600*1_000_000:
            pq=num(p.get('qty'));pb=num(p.get('position_before'));pa=num(p.get('position_after'))
            contiguous=not any(x.get('first_us',t)<t and x.get('last_us',t)>=p['first_us'] and x.get('id')!=p.get('id') for x in prior)
            consistent=all(v is not None for v in (qty,before,after,pq,pb,pa)) and abs(before-qty-after)<=.01 and abs(pb+pq-pa)<=.01
            if contiguous and consistent and pb>0 and abs(qty-pq)<=max(1,pq*.03) and abs(after-pb)<=max(1,pb*.03):
                candidate('tactical_unwind','최근 추가분 규모를 되돌린 대응 후보',f'이전 {amount(pb)} → 추가 뒤 {amount(pa)} → 이번 감량 뒤 {amount(after)} 계약입니다. 추가한 {amount(pq)}와 이번 감량 {amount(qty)} 계약이 유사해 기존 규모로 돌아가는 운영 후보입니다.', ['겹치지 않는 직전 완료 추가','전후 수량 일관성','추가/감량 규모 비교'], '수량이 같다고 동일한 계약 묶음을 매도했다고 확정할 수 없습니다. 추가분 기준 이익/손실과 전체 평균단가 기준을 구분합니다.')
        if not candidates:
            limitations.append('감량은 확인되지만 직전 평균단가가 없어 익절/손절 구분과 이유의 우선순위를 정하지 않았습니다.')
    if not candidates:
        summary='행동 기록은 있지만 지금 확보한 사전 근거로는 특정 진입 이유를 우선할 수 없습니다.' if is_entry else '물량 감소는 확인됩니다. 가격·평균단가·앞선 주문의 근거가 부족해 감량 이유를 특정하지 않았습니다.'
    else:
        summary=candidates[0]['interpretation']
    if c and c.get('sweep_low20') is False and c.get('sweep_high20') is False:
        contradictions.append('직전 1분봉에서 20분 극값 이탈 후 복귀는 관측되지 않았습니다. 그 패턴을 이번 진입의 확정 이유로 붙이지 않습니다.')
    limitations += ['체결시각은 주문 제출·결정 시각과 다를 수 있습니다. 특히 지정가의 제출 시각/미체결 주문은 미확보입니다.',
                    'Binance 현물은 시장 맥락의 대체자료입니다. BitMEX 거래량·호가 및 트레이더의 속마음을 직접 관측한 것이 아닙니다.',
                    '임계치는 연구용 초기값이며 승률·미래 매매 신호로 검증된 규칙이 아닙니다.']
    methods=[{'code':code,'status':'후보 근거 있음' if any(x['code']==code for x in candidates) else '현재 근거로 미채택'} for code in METHODS]
    result={'engine_version':ENGINE_VERSION,'event_id':event['id'],'episode_id':event.get('episode_id'),
            'time':t/1_000_000,'action':action,'title':('롱' if sign==1 else '숏' if sign else '방향 미확보')+' '+labels[action],
            'summary':summary,'facts':facts,'hypotheses':candidates,'counter_evidence':contradictions,
            'limitations':limitations,'market':context,'methods':methods,
            'cutoff':cutoff,'quantity_disclosed':completed,
            'reference_price_change_pct':move,'thresholds':{'relative_volume':2,'wick_pct':35,'range_extreme_pct':20,'tactical_size_tolerance':.03},
            'not_a_signal':True,'future_market_data_used':False}
    result['evidence_hash']=hashlib.sha256(json.dumps(result,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return result


class StudyStore(ReviewStore):
    def episodes(self,*args,**kwargs):
        rows=super().episodes(*args,**kwargs)
        for row in rows:
            # Do not silently jump to the first million-contract add.
            row['focus']=max(row['start'],row.get('year_floor',row['start']))
        return rows

    def study(self,episode,event_id='',cutoff=None):
        if cutoff not in (None,''):
            cutoff=float(cutoff)
            if not math.isfinite(cutoff) or not 1_400_000_000<=cutoff<=4_102_444_800:
                raise ValueError('올바른 복기 시각이 필요합니다.')
        else:cutoff=None
        events=self.events(str(episode))
        visible=[e for e in events if cutoff is None or e['first_us']<cutoff*1_000_000]
        selected=next((e for e in visible if e['id']==event_id),None) if event_id else (visible[-1] if cutoff is not None and visible else visible[0] if visible else None)
        if event_id and selected is None:
            raise ValueError('해당 시각에 공개되지 않은 주문이거나 포지션에 없는 주문입니다.')
        overview={'episode':str(episode),'observed_orders':len(visible),
                  'first_time':visible[0]['time'] if visible else None,
                  'increases':sum(e['role']=='Entry' for e in visible),'reductions':sum(e['role']=='Exit' for e in visible),
                  'note':'현재까지 관측된 주문 흐름입니다. 형식상 포지션 시작과 실질적인 방향 선택은 다를 수 있습니다.',
                  'last_time':max(e['end_time'] for e in visible) if cutoff is None and visible else None}
        if not selected:return {'overview':overview,'event':None}
        end=selected['first_us']//60_000_000*60
        with self.connect() as db:
            rows=db.execute('SELECT t,o,h,l,c,v FROM candles WHERE pair=? AND t>=? AND t<? ORDER BY t',(selected.get('pair'),end-2881*60,end)).fetchall()
        context=with_imported_context(closed_context(rows,selected['first_us']),selected)
        prior=[e for e in visible if e['first_us']<selected['first_us']]
        explanation=explain_event(selected,prior,context,cutoff)
        return {'overview':overview,'event':explanation}
