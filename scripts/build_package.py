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
    files.extend(p for p in (ROOT / name).rglob('*') if p.is_file() and not p.is_symlink()
                 and not blocked_parts.intersection(p.relative_to(ROOT).parts)
                 and p.suffix.lower() not in blocked_suffixes and not p.name.startswith('.env'))
files = sorted(set(p for p in files if p.exists()))
# prepare_vendor.py installs to the repository-root vendor/ directory.
# /vendor/ in the browser is a server route, not web/vendor/ on disk.
required_vendor = {'lightweight-charts.js', 'manifest.json', 'LICENSE', 'NOTICE'}
if any(not (ROOT / 'vendor' / name).is_file() for name in required_vendor):
    raise RuntimeError('Missing chart library/notices. Run python scripts/prepare_vendor.py first.')
vendor_manifest = json.loads((ROOT / 'vendor' / 'manifest.json').read_text(encoding='utf-8'))
if vendor_manifest.get('version') != '5.0.9':
    raise RuntimeError('Unexpected chart library version')
for name in ('lightweight-charts.js', 'LICENSE', 'NOTICE'):
    digest = hashlib.sha256((ROOT / 'vendor' / name).read_bytes()).hexdigest()
    if digest != vendor_manifest.get('files', {}).get(name):
        raise RuntimeError('Chart library/notice integrity mismatch: ' + name)
try:
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
except (OSError, subprocess.CalledProcessError):
    commit = 'not-a-git-checkout'
manifest = {'version': '0.3.0', 'commit': commit,
            'user_data_included': False, 'python_required': '3.10+',
            'entrypoint_windows': 'start_windows.bat',
            'files_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
encoded = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
(out / 'release-manifest.json').write_bytes(encoded)
with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, Path('AOA-Whale-Viewer') / p.relative_to(ROOT))
    z.writestr('AOA-Whale-Viewer/release-manifest.json', encoded)
with zipfile.ZipFile(target) as z:
    if z.testzip() is not None:
        raise RuntimeError('ZIP integrity check failed')
    for name in required_vendor:
        if 'AOA-Whale-Viewer/vendor/' + name not in z.namelist():
            raise RuntimeError('Runtime ZIP is missing vendor/' + name)
    for name, expected in manifest['files_sha256'].items():
        if hashlib.sha256(z.read('AOA-Whale-Viewer/' + name)).hexdigest() != expected:
            raise RuntimeError('Packaged file differs from manifest: ' + name)
digest = hashlib.sha256(target.read_bytes()).hexdigest()
(target.with_name(target.name + '.sha256')).write_text(digest + '  ' + target.name + '\n', encoding='utf-8')
print('Package:', target, 'bytes:', target.stat().st_size, 'sha256:', digest, 'commit:', commit)
