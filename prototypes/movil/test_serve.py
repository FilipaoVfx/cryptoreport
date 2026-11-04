"""Regresión: una visita nueva al túnel debe funcionar sin clave ni cookie."""
import importlib.util
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("prototype_server", Path(__file__).with_name("serve.py"))
server_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_module)


class PublicTunnel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), server_module.Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_clean_url_from_new_device(self):
        req = urllib.request.Request(self.base + "/1b-bitacora/", headers={"Cf-Connecting-Ip": "203.0.113.1"})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)
            self.assertIsNone(response.headers.get("Set-Cookie"))
            self.assertIn(b'Bit', response.read())

    def test_assets_work_without_browser_session(self):
        req = urllib.request.Request(self.base + "/shared/core.js", headers={"X-Forwarded-For": "203.0.113.2"})
        with urllib.request.urlopen(req) as response:
            self.assertEqual(response.status, 200)

    def test_private_server_files_remain_inaccessible(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(self.base + "/serve.py")
        self.assertEqual(error.exception.code, 404)
        error.exception.close()


if __name__ == "__main__":
    unittest.main()
