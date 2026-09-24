"""Exercise the extracted ZIP in a path containing spaces and Korean characters."""
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent

def main():
    with tempfile.TemporaryDirectory(prefix='AOA packaged ') as td:
        folder=Path(td)/'한글 경로';folder.mkdir()
        with zipfile.ZipFile(ROOT/'dist/AOA-Whale-Viewer.zip') as z:
            z.extractall(folder)
        app=folder/'AOA-Whale-Viewer'
        subprocess.run([sys.executable,'run.py','--self-check'],cwd=app,check=True)
        subprocess.run([sys.executable,'-m','tests.browser_launch_test'],cwd=app,check=True)
        target=ROOT/'test-results';target.mkdir(exist_ok=True)
        for p in (app/'test-results').glob('*'):
            if p.is_file(): (target/('packaged-'+p.name)).write_bytes(p.read_bytes())

if __name__=='__main__':main()
