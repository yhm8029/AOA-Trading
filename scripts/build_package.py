"""Package the tested runtime, never local-data, credentials or font files."""
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = ROOT / 'dist'
out.mkdir(exist_ok=True)
target = out / 'AOA-Whale-Viewer.zip'
roots = ['aoa', 'web', 'scripts', 'docs', 'tests', 'vendor']
files = [ROOT / x for x in ['run.py', 'start_windows.bat', 'start_unix.sh', 'README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', '.gitignore']]
blocked_parts = {'__pycache__', 'local-data', '.git', '.venv', 'node_modules', 'test-results'}
blocked_suffixes = {'.pyc', '.sqlite3', '.sqlite', '.db', '.ttf', '.otf', '.woff', '.woff2'}
for name in roots:
    files.extend(p for p in (ROOT / name).rglob('*') if p.is_file()
                 and not blocked_parts.intersection(p.relative_to(ROOT).parts)
                 and p.suffix.lower() not in blocked_suffixes and not p.name.startswith('.env'))
files = sorted(set(p for p in files if p.exists()))
try:
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
except (OSError, subprocess.CalledProcessError):
    commit = 'not-a-git-checkout'
manifest = {'version': '0.3.0', 'commit': commit,
            'user_data_included': False, 'python_required': '3.10+',
            'entrypoint_windows': 'start_windows.bat',
            'files_sha256': {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
(out / 'release-manifest.json').write_bytes(encoded)
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, Path('AOA-Whale-Viewer') / p.relative_to(ROOT))
    z.writestr('AOA-Whale-Viewer/release-manifest.json', encoded)
with zipfile.ZipFile(target) as z:
    assert z.testzip() is None, 'ZIP integrity check failed'
    assert 'AOA-Whale-Viewer/web/vendor/lightweight-charts.js' in z.namelist(), 'Run prepare_vendor.py first'
digest = hashlib.sha256(target.read_bytes()).hexdigest()
(target.with_name(target.name + '.sha256')).write_text(digest + '  ' + target.name + '\n', encoding='utf-8')
print('Package:', target, 'bytes:', target.stat().st_size, 'sha256:', digest, 'commit:', commit)
