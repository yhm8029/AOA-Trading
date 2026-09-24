"""Build source-plus-chart-assets ZIP. Deliberately excludes every user dataset."""
from pathlib import Path
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DIST=ROOT/'dist'
DIST.mkdir(exist_ok=True)
roots=['aoa','web','docs','tests','scripts']
top=['app.py','prepare_assets.py','start_windows.bat','start_unix.sh','README.md','LICENSE','THIRD_PARTY_NOTICES.md','AGENTS.md','.gitignore']
files=[ROOT/x for x in top if (ROOT/x).is_file()]
for r in roots:
    for p in (ROOT/r).rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.sqlite3','.csv','.gz','.zip','.xlsx'):
            files.append(p)
assert (ROOT/'web/vendor/lightweight-charts.js') in files
out=DIST/'AOA-Whale-Viewer.zip'
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for path in sorted(files):
        rel=path.relative_to(ROOT)
        assert not {'data','local-data','imports','exports','inbox'}.intersection(rel.parts)
        z.write(path,'AOA-Whale-Viewer/'+str(rel).replace('\\','/'))
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    assert 'AOA-Whale-Viewer/web/vendor/lightweight-charts.js' in z.namelist()
    assert 'AOA-Whale-Viewer/start_windows.bat' in z.namelist()
print(json.dumps({'package':out.name,'bytes':out.stat().st_size,'files':len(files),'contains_user_data':False},indent=2))
