"""Fetch pinned official chart bundle once; all app/data requests remain local."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import tarfile
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse

VERSION='5.2.1'
ROOT=Path(__file__).resolve().parent
DEST=ROOT/'web'/'vendor'


def download(url,limit):
    with urlopen(Request(url,headers={'User-Agent':'AOA-Whale-Viewer/0.1'}),timeout=40) as r:
        body=r.read(limit+1)
    if len(body)>limit:
        raise RuntimeError('Asset download exceeds limit')
    return body


def ensure_assets():
    manifest=DEST/'manifest.json'
    script=DEST/'lightweight-charts.js'
    if manifest.exists() and script.exists():
        data=json.loads(manifest.read_text(encoding='utf-8'))
        if data.get('version')==VERSION and hashlib.sha256(script.read_bytes()).hexdigest()==data.get('script_sha256'):
            return data
        raise RuntimeError('Chart asset hash mismatch. Remove web/vendor then restart to re-download.')
    print('Downloading official Lightweight Charts '+VERSION+' (first run only)...',flush=True)
    metadata=json.loads(download('https://registry.npmjs.org/lightweight-charts/'+VERSION,200000))
    if metadata.get('version')!=VERSION:
        raise RuntimeError('NPM package version mismatch')
    tarball=metadata['dist']['tarball']
    u=urlparse(tarball)
    if u.scheme!='https' or u.hostname!='registry.npmjs.org':
        raise RuntimeError('Unexpected package source')
    body=download(tarball,15*1024*1024)
    integrity=metadata['dist']['integrity']
    if integrity!='sha512-'+base64.b64encode(hashlib.sha512(body).digest()).decode():
        raise RuntimeError('Official package integrity verification failed')
    DEST.mkdir(parents=True,exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as tf:
        for member,target in [('package/dist/lightweight-charts.standalone.production.js','lightweight-charts.js'),('package/LICENSE','LICENSE'),('package/NOTICE','NOTICE')]:
            f=tf.extractfile(member)
            if f is None:
                raise RuntimeError('Missing package member '+member)
            data=f.read(3000000)
            (DEST/target).write_bytes(data)
    data=dict(version=VERSION,source=tarball,integrity=integrity,
        script_sha256=hashlib.sha256(script.read_bytes()).hexdigest())
    manifest.write_text(json.dumps(data,indent=2),encoding='utf-8')
    return data

if __name__=='__main__':
    print(json.dumps(ensure_assets(),indent=2))
