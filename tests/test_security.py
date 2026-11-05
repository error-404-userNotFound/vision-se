import unittest
from flask import Flask, jsonify
from security import configure_pairing

BASE = 'https://localhost'


class PairingTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.code = configure_pairing(self.app)
        self.app.add_url_rule('/settings', view_func=lambda: jsonify(ok=True), methods=['GET', 'POST'])
        self.client = self.app.test_client()

    def pair(self, code=None, **kwargs):
        return self.client.post('/pair', base_url=BASE, data={'code': code or self.code}, **kwargs)

    def test_protects_api_static_and_page(self):
        for path in ['/settings', '/screen.mjpeg', '/static/js/host.js', '/cursor', '/signal/host_offer']:
            self.assertEqual(self.client.get(path, base_url=BASE).status_code, 401)
        self.assertEqual(self.client.get('/host', base_url=BASE).status_code, 302)

    def test_pairing_enables_requests_with_secure_cookie(self):
        response = self.pair()
        self.assertEqual(response.status_code, 302)
        cookie = response.headers['Set-Cookie']
        for attr in ['Secure', 'HttpOnly', 'SameSite=Strict']:
            self.assertIn(attr, cookie)
        self.assertEqual(self.client.get('/settings', base_url=BASE).status_code, 200)
        self.assertEqual(self.client.post('/settings', base_url=BASE).status_code, 200)

    def test_wrong_code_cannot_pair(self):
        self.assertEqual(self.pair('wrong').status_code, 401)
        self.assertEqual(self.client.get('/settings', base_url=BASE).status_code, 401)

    def test_unicode_input_is_handled(self):
        self.assertEqual(self.pair('错误').status_code, 401)

    def test_cross_origin_pairing_and_writes_rejected(self):
        self.assertEqual(self.pair(headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.pair()
        self.assertEqual(self.client.post('/settings', base_url=BASE,
                         headers={'Origin': 'https://evil.example'}).status_code, 403)
        self.assertEqual(self.client.post('/settings', base_url=BASE,
                         headers={'Origin': BASE}).status_code, 200)

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.pair('wrong').status_code, 401)
        self.assertEqual(self.pair().status_code, 429)

    def test_redirect_target_is_allowlisted(self):
        response = self.client.post('/pair?next=https://evil.example', base_url=BASE,
                                    data={'code': self.code})
        self.assertEqual(response.headers['Location'], '/')

    def test_new_process_secret_invalidates_session(self):
        self.pair()
        self.app.secret_key = b'a different process secret'
        self.assertEqual(self.client.get('/settings', base_url=BASE).status_code, 401)

    def test_pair_page_headers(self):
        response = self.client.get('/pair', base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')


if __name__ == '__main__':
    unittest.main()
