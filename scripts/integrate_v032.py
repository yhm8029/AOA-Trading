"""Final exact-anchor correction for replay outcome status text."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    p=ROOT/'web/app.mjs';s=p.read_text(encoding='utf-8')
    edits=[
      ("const vals=S.cutoff!=null?[['방향'", "const vals=S.cutoff!=null&&!outcomeAvailable(p,S.cutoff)?[['방향'"),
      ("S.cutoff!=null?' · 복기: 미래 봉·최종 성과 숨김':''", "S.cutoff!=null?(outcomeAvailable(S.performance,S.cutoff)?' · 복기: 종료 포지션 성과 공개':' · 복기: 미래 봉·최종 성과 숨김'):''"),
      ("if(S.cutoff==null&&p){$('performanceNote')", "if(outcomeAvailable(p,S.cutoff)){$('performanceNote')"),
    ]
    for old,new in edits:
        if s.count(old)!=1:raise RuntimeError('Expected exact replay status anchor: '+old)
        s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
if __name__=='__main__':main()
