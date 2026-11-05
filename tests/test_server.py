import unittest
import tempfile
import subprocess
import ssl
import urllib.request
from pathlib import Path
from unittest.mock import patch
import server

BASE = 'https://localhost'


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_import_does_not_start_server(self):
        self.assertIsNone(server.HTTP_SERVER)
        self.assertIsNone(server.SERVER_THREAD)

    def test_missing_certificates_fail_before_side_effects(self):
        with patch.object(server, 'CERT_FILE', '/missing/vision-se-cert.pem'):
            with self.assertRaisesRegex(RuntimeError, 'TLS files missing'):
                server.start_server_background()
        self.assertIsNone(server.HTTP_SERVER)

    def test_paired_pages_settings_and_vendor(self):
        self.client.post('/pair', base_url=BASE, data={'code': server.PAIRING_CODE})
        for path in ['/', '/host', '/gesture_host', '/settings', '/static/vendor/three/build/three.module.js']:
            with self.subTest(path=path):
                response = self.client.get(path, base_url=BASE)
                self.assertEqual(response.status_code, 200)
                response.close()

    def test_cursor_does_not_move_before_pairing(self):
        with patch.object(server.pyautogui, 'moveTo') as move:
            response = self.client.post('/cursor', base_url=BASE, json={'x': 10, 'y': 20})
            self.assertEqual(response.status_code, 401)
            move.assert_not_called()

    def test_https_start_pair_and_stop(self):
        with tempfile.TemporaryDirectory() as temp:
            cert, key = str(Path(temp) / 'cert.pem'), str(Path(temp) / 'key.pem')
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', key, '-out', cert, '-days', '1', '-subj', '/CN=localhost',
                            '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            with patch.multiple(server, CERT_FILE=cert, KEY_FILE=key,
                                SERVER_PORT=0, BIND_HOST='127.0.0.1'), \
                    patch.object(server, 'start_phone_link_monitor_once'), \
                    patch.object(server, 'start_gesture_thread_once'):
                try:
                    server.start_server_background()
                    port = server.HTTP_SERVER.server_port
                    context = ssl.create_default_context(cafile=cert)
                    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                                         urllib.request.HTTPSHandler(context=context))
                    with opener.open(f'https://127.0.0.1:{port}/pair', timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertIn(b'Pair with Vision SE', response.read())
                finally:
                    server.stop_server_background()
                self.assertIsNone(server.HTTP_SERVER)
                self.assertIsNone(server.SERVER_THREAD)

    def test_port_helper_never_kills_other_processes(self):
        with patch.object(server.os, 'kill') as kill:
            killed, errors = server.free_port(8443)
            self.assertEqual(killed, [])
            self.assertTrue(errors)
            kill.assert_not_called()

    def test_oversized_camera_upload_rejected(self):
        self.client.post('/pair', base_url=BASE, data={'code': server.PAIRING_CODE})
        response = self.client.post('/phone_cam_frame', base_url=BASE,
                                    data=b'x' * (4 * 1024 * 1024 + 1),
                                    content_type='image/jpeg')
        self.assertEqual(response.status_code, 413)


if __name__ == '__main__':
    unittest.main()
