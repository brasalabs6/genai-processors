import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from urllib import request

from leonidas import api
from leonidas import http_server
from leonidas import log_store


class FakeControlApi:

  async def dispatch(self, method, path, body=None):
    return api.ApiResponse(
        200,
        json.dumps({'data': {'method': method, 'path': path, 'body': body}}),
    )


class HttpServerTest(unittest.IsolatedAsyncioTestCase):

  async def asyncSetUp(self):
    self.temp_dir = tempfile.TemporaryDirectory()
    root = Path(self.temp_dir.name)
    self.loop = asyncio.get_running_loop()
    (root / 'index.html').write_text('<h1>Leonidas</h1>', encoding='utf-8')
    self.server = http_server.create_server(
        host='127.0.0.1',
        port=0,
        web_root=root,
        control_api=FakeControlApi(),
        event_loop=self.loop,
        log_bus=log_store.LogBus(),
    )
    self.thread = http_server.serve_in_thread(self.server)
    host, port = self.server.server_address
    self.base_url = f'http://{host}:{port}'

  async def asyncTearDown(self):
    self.server.shutdown()
    self.server.server_close()
    self.thread.join(timeout=2)
    self.temp_dir.cleanup()

  async def test_serves_vite_build_and_spa_fallback(self):
    def fetch(path):
      with request.urlopen(self.base_url + path, timeout=2) as response:
        return response.status, response.read()

    status, body = await asyncio.to_thread(fetch, '/settings')
    self.assertEqual(status, 200)
    self.assertIn(b'Leonidas', body)

  async def test_routes_json_to_control_api(self):
    def fetch():
      with request.urlopen(
          self.base_url + '/api/v1/session', timeout=2
      ) as response:
        return response.status, json.loads(response.read())

    status, body = await asyncio.to_thread(fetch)
    self.assertEqual(status, 200)
    self.assertEqual(body['data']['method'], 'GET')

  async def test_allows_same_origin_when_running_on_non_default_port(self):
    def fetch():
      host, port = self.server.server_address
      req = request.Request(
          f'http://{host}:{port}/api/v1/session',
          headers={'Origin': f'http://127.0.0.1:{port}'},
      )
      with request.urlopen(req, timeout=2) as response:
        return response.status, json.loads(response.read())

    status, body = await asyncio.to_thread(fetch)
    self.assertEqual(status, 200)
    self.assertEqual(body['data']['method'], 'GET')

  async def test_rejects_unallowlisted_origin(self):
    def fetch():
      host, port = self.server.server_address
      req = request.Request(
          f'http://{host}:{port}/api/v1/session',
          headers={'Origin': 'http://evil.example'},
      )
      try:
        request.urlopen(req, timeout=2)
      except request.HTTPError as exc:
        return exc.code, json.loads(exc.read())
      raise AssertionError('request unexpectedly succeeded')

    status, body = await asyncio.to_thread(fetch)
    self.assertEqual(status, 403)
    self.assertEqual(body['error']['code'], 'origin_forbidden')

  def test_rejects_non_loopback_bind(self):
    with self.assertRaisesRegex(ValueError, '127.0.0.1'):
      http_server.create_server(
          host='0.0.0.0',
          port=0,
          web_root=Path(self.temp_dir.name),
          control_api=FakeControlApi(),
          event_loop=self.loop,
          log_bus=log_store.LogBus(),
      )


if __name__ == '__main__':
  unittest.main()
