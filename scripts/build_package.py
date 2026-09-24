"""Build a source/runtime ZIP; explicitly exclude all user data and test databases."""
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
out=ROOT/'dist';out.mkdir(exist_ok=True)
target=out/'AOA-Whale-Viewer.zip'
roots=['aoa','web','scripts','docs','tests','vendor']
files=[ROOT/x for x in ['run.py','start_windows.bat','start_unix.sh','README.md','LICENSE','THIRD_PARTY_NOTICES.md','.gitignore']]
for name in roots:
    files.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in {'.pyc','.sqlite3'})
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:
        if p.exists():z.write(p,Path('AOA-Whale-Viewer')/p.relative_to(ROOT))
print('Package:',target,'bytes:',target.stat().st_size)
