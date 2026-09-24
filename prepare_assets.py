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
# npm 5.2.1 does not ship NOTICE. Exact notice read from the matching upstream tag:
# https://github.com/tradingview/lightweight-charts/blob/v5.2.1/NOTICE
NOTICE='TradingView Lightweight Charts™\nCopyright (с) 2025 TradingView, Inc. https://www.tradingview.com/\n'


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
        checks=data.get('files',{})
        valid=data.get('version')==VERSION and all(
            (DEST/name).is_file() and hashlib.sha256((DEST/name).read_bytes()).hexdigest()==checks.get(name)
            for name in ('lightweight-charts.js','LICENSE','NOTICE'))
        if valid:
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
    output={}
    with tarfile.open(fileobj=io.BytesIO(body),mode='r:gz') as tf:
        for member,target in [('package/dist/lightweight-charts.standalone.production.js','lightweight-charts.js'),('package/LICENSE','LICENSE')]:
            f=tf.extractfile(member)
            if f is None:
                raise RuntimeError('Missing package member '+member)
            with f:
                output[target]=f.read(3000000)
        if 'package/NOTICE' in tf.getnames():
            with tf.extractfile('package/NOTICE') as f:
                output['NOTICE']=f.read(100000)
        else:
            output['NOTICE']=NOTICE.encode('utf-8')
    DEST.mkdir(parents=True,exist_ok=True)
    checks={}
    for name,content in output.items():
        temp=DEST/(name+'.partial')
        temp.write_bytes(content);temp.replace(DEST/name)
        checks[name]=hashlib.sha256(content).hexdigest()
    data=dict(version=VERSION,source=tarball,integrity=integrity,files=checks,
              notice_source='https://github.com/tradingview/lightweight-charts/blob/v5.2.1/NOTICE')
    temp=DEST/'manifest.json.partial'
    temp.write_text(json.dumps(data,indent=2),encoding='utf-8');temp.replace(manifest)
    return data

if __name__=='__main__':
    print(json.dumps(ensure_assets(),indent=2))
