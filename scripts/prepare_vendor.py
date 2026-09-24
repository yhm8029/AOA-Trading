"""Install pinned LWC, verify npm SHA-512, preserve exact upstream notices."""
import base64
import hashlib
import io
import json
import tarfile
import urllib.request
from pathlib import Path

VERSION='5.0.9'
ROOT=Path(__file__).resolve().parent.parent
# Exact NOTICE verified from tradingview/lightweight-charts tag v5.0.9.
# Git blob 37971d0b7b5ec7110b759e73301c8fede45db174.
# npm's v5.0.9 package omits the repository's NOTICE file.
UPSTREAM_NOTICE='TradingView Lightweight Charts™\nCopyright (с) 2025 TradingView, Inc. https://www.tradingview.com/\n'


def install():
    vendor=ROOT/'vendor'; vendor.mkdir(exist_ok=True)
    manifest=vendor/'manifest.json'
    if manifest.exists():
        try:
            recorded=json.loads(manifest.read_text(encoding='utf-8'))
            if recorded['version']==VERSION and all((vendor/name).exists() and hashlib.sha256((vendor/name).read_bytes()).hexdigest()==sha for name,sha in recorded['files'].items()):
                return
        except (ValueError,KeyError,OSError):
            pass
    def fetch(url):
        with urllib.request.urlopen(url,timeout=45) as r:
            return r.read(4*1024*1024)
    meta=json.loads(fetch('https://registry.npmjs.org/lightweight-charts/'+VERSION))
    url=meta['dist']['tarball']
    if not url.startswith('https://registry.npmjs.org/lightweight-charts/'):
        raise ValueError('Unexpected package source')
    raw=fetch(url)
    expected=meta['dist']['integrity']
    actual='sha512-'+base64.b64encode(hashlib.sha512(raw).digest()).decode()
    if actual!=expected:
        raise ValueError('Chart library integrity mismatch')
    outputs={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
        for remote,local in [('package/dist/lightweight-charts.standalone.production.js','lightweight-charts.js'),('package/LICENSE','LICENSE')]:
            member=archive.getmember(remote)
            if not member.isfile() or member.size>3*1024*1024:
                raise ValueError('Unexpected package member')
            data=archive.extractfile(member).read()
            (vendor/local).write_bytes(data)
            outputs[local]=hashlib.sha256(data).hexdigest()
        notice=UPSTREAM_NOTICE.encode('utf-8')
        for candidate in ('package/NOTICE','package/NOTICE.md','package/NOTICE.txt'):
            if candidate in archive.getnames():
                notice=archive.extractfile(candidate).read()
                break
        (vendor/'NOTICE').write_bytes(notice)
        outputs['NOTICE']=hashlib.sha256(notice).hexdigest()
    manifest.write_text(json.dumps({'version':VERSION,'integrity':expected,'files':outputs},indent=2),encoding='utf-8')
    print('Lightweight Charts',VERSION,'verified and installed locally.')

if __name__=='__main__':
    install()
