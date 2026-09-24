"""Build and verify the distributable; exclude private data, keys, and fonts."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from aoa.version import VERSION
out=ROOT/'dist';out.mkdir(exist_ok=True)
target=out/'AOA-Whale-Viewer.zip'
roots=['aoa','web','scripts','docs','tests','vendor']
files=[ROOT/x for x in ['run.py','start_windows.bat','start_with_existing_data.bat','start_unix.sh','README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitignore']]
blocked_parts={'__pycache__','local-data','.git','.venv','node_modules','test-results'}
blocked_suffixes={'.pyc','.sqlite3','.sqlite','.db','.ttf','.otf','.woff','.woff2'}
for name in roots:
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and not blocked_parts.intersection(p.relative_to(ROOT).parts) and p.suffix.lower() not in blocked_suffixes and not p.name.startswith('.env'))
files=sorted(set(p for p in files if p.exists()))
try:commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
except (OSError,subprocess.CalledProcessError):commit='not-a-git-checkout'
manifest={'version':VERSION,'commit':commit,'user_data_included':False,'python_required':'3.10+',
          'entrypoint_windows':'start_windows.bat','files_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
encoded=json.dumps(manifest,ensure_ascii=False,indent=2).encode('utf-8');(out/'release-manifest.json').write_bytes(encoded)
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:z.write(p,Path('AOA-Whale-Viewer')/p.relative_to(ROOT))
    z.writestr('AOA-Whale-Viewer/release-manifest.json',encoded)
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None,'ZIP integrity failed'
    names=set(z.namelist())
    assert 'AOA-Whale-Viewer/vendor/lightweight-charts.js' in names,'Run prepare_vendor.py first'
    for name,digest in manifest['files_sha256'].items():
        assert hashlib.sha256(z.read('AOA-Whale-Viewer/'+name)).hexdigest()==digest,name
    for name in names:
        assert not blocked_parts.intersection(Path(name).parts),name
        assert Path(name).suffix.lower() not in blocked_suffixes,name
sha=hashlib.sha256(target.read_bytes()).hexdigest()
(target.with_name(target.name+'.sha256')).write_text(sha+'  '+target.name+'\n',encoding='utf-8')
print('Package:',target,'bytes:',target.stat().st_size,'sha256:',sha,'commit:',commit)
