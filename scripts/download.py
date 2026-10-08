#!/usr/bin/env python3
"""Download manifest assets into this project's data/raw; never execute source code."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import gzip
import hashlib
import json
from pathlib import Path
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_md5(path, asset):
    """Compare with the publisher's md5 file (first token), e.g. NGDC's <accession>_md5.txt."""
    request = Request(asset['md5_url'], headers={'User-Agent': 'DeepPBI-provenance-audit/1.0'})
    with urlopen(request, timeout=45) as response:
        expected = response.read().decode().split()[0].lower()
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'md5').hexdigest()
    if actual != expected:
        raise ValueError('MD5 differs from publisher')
    return actual


def destination(root, relative):
    target = (root / relative).resolve()
    if not target.is_relative_to((root / 'data/raw').resolve()):
        raise ValueError('Destination must be inside data/raw')
    return target


def validate(path, kind):
    with path.open('rb') as stream:
        head = stream.read(1024).lstrip()
    if not head or head.startswith(b'version https://git-lfs.github.com/spec/'):
        raise ValueError('Empty file or unresolved Git LFS pointer')
    if kind != 'html' and (head.lower().startswith((b'<!doctype html', b'<html'))):
        raise ValueError('HTML response instead of data')
    if kind == 'fasta' and not head.startswith(b'>'):
        raise ValueError('Not FASTA')
    if kind == 'gzip_fasta':
        with gzip.open(path, 'rb') as stream:
            if stream.read(1) != b'>':
                raise ValueError('Not gzipped FASTA')
            while stream.read(1024 * 1024):
                pass
    if kind in ('zip', 'xlsx'):
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad:
                raise ValueError('Corrupt archive member: ' + bad)
    if kind == 'json':
        json.loads(path.read_text())


def fetch(asset, root=ROOT, attempts=3):
    """Return a receipt; failure preserves any existing destination and raises."""
    target = destination(root, asset['path'])
    receipt_path = target.with_name(target.name + '.receipt.json')
    if target.exists() and receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get('url') == asset['url'] and digest(target) == receipt['sha256']:
            validate(target, asset.get('kind', 'binary'))
            if asset.get('md5_url') and not receipt.get('md5'):
                receipt['md5'] = check_md5(target, asset)
                receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
            return dict(receipt, status='verified_existing')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.part')
    for attempt in range(attempts):
        try:
            request = Request(asset['url'], headers={'User-Agent': 'DeepPBI-provenance-audit/1.0',
                                                     **asset.get('headers', {})})
            with urlopen(request, timeout=45) as response, temporary.open('wb') as stream:
                final_url = response.url
                expected = response.headers.get('Content-Length')
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            if expected is not None and temporary.stat().st_size != int(expected):
                raise ValueError('Incomplete HTTP body')
            validate(temporary, asset.get('kind', 'binary'))
            checksum = digest(temporary)
            if asset.get('sha256') and checksum != asset['sha256']:
                raise ValueError('Checksum differs from manifest')
            if asset.get('bytes') is not None and temporary.stat().st_size != asset['bytes']:
                raise ValueError('Size differs from manifest')
            md5 = check_md5(temporary, asset) if asset.get('md5_url') else None
            receipt = dict(asset, final_url=final_url, sha256=checksum,
                           bytes=temporary.stat().st_size, status='downloaded',
                           **({'md5': md5} if md5 else {}),
                           retrieved_at=datetime.now(timezone.utc).isoformat())
            temporary.replace(target)
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
            return receipt
        except Exception as error:
            if isinstance(error, HTTPError):
                error.close()
            temporary.unlink(missing_ok=True)
            if attempt + 1 == attempts:
                raise
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--list', action='store_true')
    group.add_argument('--source')
    group.add_argument('--all', action='store_true')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'manifest.json')
    parser.add_argument('--jobs', type=int, default=1, help='Concurrent downloads (default: 1)')
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error('--jobs must be at least 1')
    assets = json.loads(args.manifest.read_text())
    paths = [destination(ROOT, a['path']) for a in assets]
    if len(paths) != len(set(paths)):
        parser.error('Duplicate manifest destinations')
    selected = [a for a in assets if not args.source or a['source'] == args.source]
    if not selected:
        parser.error('Unknown source')
    if args.list:
        for a in selected:
            print(a['source'], a['path'], a.get('status', 'available'))
        return
    (ROOT / 'logs').mkdir(exist_ok=True)
    failures = 0
    def retrieve(asset):
        if asset.get('status') in ('blocked', 'unavailable'):
            return dict(asset, checked_at=datetime.now(timezone.utc).isoformat())
        try:
            return fetch(asset)
        except Exception as error:
            return dict(asset, status='blocked', error=str(error),
                        checked_at=datetime.now(timezone.utc).isoformat())

    with (ROOT / 'logs/downloads.jsonl').open('a') as log:
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            for a, result in zip(selected, pool.map(retrieve, selected)):
                failures += result['status'] == 'blocked' and a.get('status') not in ('blocked', 'unavailable')
                log.write(json.dumps(result, ensure_ascii=False) + '\n')
                log.flush()
                print(result['status'], a['path'], result.get('error', ''), flush=True)
    raise SystemExit(bool(failures))


if __name__ == '__main__':
    main()
