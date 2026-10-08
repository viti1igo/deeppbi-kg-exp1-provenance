import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location('download', Path(__file__).resolve().parents[1] / 'scripts/download.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        bodies = {'/ok': b'>ABC.1\nACGT\n', '/html': b'<html>error</html>', '/lfs': b'version https://git-lfs.github.com/spec/v1\n',
                  '/good.md5': hashlib.md5(b'>ABC.1\nACGT\n').hexdigest().encode() + b'  a.fa\n', '/bad.md5': b'0' * 32 + b'  a.fa\n'}
        if self.path == '/missing':
            self.send_error(404)
            return
        body = bodies.get(self.path, b'>ABC.1\nACGT\n')
        self.send_response(200)
        self.send_header('Content-Length', str(len(body) + (10 if self.path == '/short' else 0)))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
    def test_download_repeat_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a = dict(url=f'http://127.0.0.1:{self.server.server_port}/ok', path='data/raw/a.fa', kind='fasta')
            self.assertEqual(d.fetch(a,root,1)['status'],'downloaded')
            self.assertEqual(d.fetch(a,root,1)['status'],'verified_existing')
            (root/a['path']).write_text('corrupt')
            self.assertEqual(d.fetch(a,root,1)['status'],'downloaded')
            self.assertEqual(d.digest(root/a['path']),hashlib.sha256(b'>ABC.1\nACGT\n').hexdigest())
    def test_failures_leave_no_final_or_partial_file(self):
        for endpoint in ['html','lfs','missing','short']:
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                a=dict(url=f'http://127.0.0.1:{self.server.server_port}/{endpoint}',path='data/raw/a.fa',kind='fasta')
                with self.assertRaises(Exception):d.fetch(a,root,1)
                self.assertFalse((root/a['path']).exists())
                self.assertFalse((root/'data/raw/a.fa.part').exists())
    def test_paths_and_checksum(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for path in ['../escape','data/raw/../../escape','/tmp/escape']:
                with self.assertRaises(ValueError):d.destination(root,path)
            a=dict(url=f'http://127.0.0.1:{self.server.server_port}/ok',path='data/raw/a.fa',kind='fasta',sha256='wrong')
            with self.assertRaises(ValueError):d.fetch(a,root,1)
    def test_publisher_md5(self):
        base=f'http://127.0.0.1:{self.server.server_port}'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            a=dict(url=base+'/ok',path='data/raw/a.fa',kind='fasta',md5_url=base+'/bad.md5')
            with self.assertRaises(ValueError):d.fetch(a,root,1)
            self.assertFalse((root/a['path']).exists())
            d.fetch(dict(a,md5_url=None),root,1)
            self.assertNotIn('md5',d.json.loads((root/'data/raw/a.fa.receipt.json').read_text()))
            receipt=d.fetch(dict(a,md5_url=base+'/good.md5'),root,1)
            self.assertEqual(receipt['status'],'verified_existing')
            self.assertEqual(receipt['md5'],hashlib.md5(b'>ABC.1\nACGT\n').hexdigest())

if __name__ == '__main__':unittest.main()
