import sys
import json
import time
import unittest

from server import Server, ConfigurationException


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.server = Server([
            {
                '/testing': {
                    'headers': {
                        'X-Sample': '^ab[0-9]+$'
                    },
                    'body': {
                        'key': 'value',
                        'item': {
                            'prop': '^[0-9]*$'
                        }
                    }
                }
            }
        ])

        self.server.app.testing = True
        self.client = self.server.app.test_client()

    def test_valid_request(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value',
            'item': {
                'prop': '123'
            }
        }

        self._check(200, headers, body)

    def test_valid_request_without_optional(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value'
        }

        self._check(200, headers, body)

    def test_valid_request_with_list(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value',
            'item': [
                {
                    'prop': '001'
                },
                {
                    'prop': '002'
                },
                {
                    'prop': '999'
                }
            ]
        }

        self._check(200, headers, body)

    def test_invalid_headers(self):
        headers = {
            'X-Sample': 'invalid'
        }

        body = {
            'key': 'value',
            'item': {
                'prop': '123'
            }
        }

        self._check(409, headers, body)

    def test_invalid_body(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value',
            'item': 'prop'
        }

        self._check(409, headers, body)

    def test_invalid_body_second_level(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value',
            'item': {
                'prop': 'invalid'
            }
        }

        self._check(409, headers, body)

    def test_invalid_body_with_list(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value',
            'item': [
                {
                    'prop': '001'
                },
                {
                    'prop': '002'
                },
                {
                    'prop': 'notanumber'
                }
            ]
        }

        self._check(409, headers, body)

    def _check(self, expected_status_code, headers, body):
        response = self.client.post('/testing',
                                    headers=headers, data=json.dumps(body),
                                    content_type='application/json')

        self.assertEqual(expected_status_code, response.status_code)

    def test_non_json_request(self):
        response = self.client.post('/testing', data='plain text', content_type='text/plain')

        self.assertEqual(400, response.status_code)

    def test_non_supported_method(self):
        headers = {
            'X-Sample': 'ab001'
        }

        body = {
            'key': 'value',
            'item': {
                'prop': '123'
            }
        }

        response = self.client.put('/testing',
                                   headers=headers, data=json.dumps(body),
                                   content_type='application/json')

        self.assertEqual(405, response.status_code)

    def test_missing_endpoint_configuration_throws_exception(self):
        self.assertRaises(ConfigurationException, Server, None)
        self.assertRaises(ConfigurationException, Server, list())

    def test_missing_endpoint_route_throws_exception(self):
        self.assertRaises(ConfigurationException, Server, [{None: {'method': 'GET'}}])
        self.assertRaises(ConfigurationException, Server, [{'': {'method': 'GET'}}])

    def test_empty_endpoint_settings_accept_empty_body(self):
        server = Server([{'/empty': None}])

        server.app.testing = True
        client = server.app.test_client()

        response = client.post('/empty')

        self.assertEqual(200, response.status_code)

    def test_get_request(self):
        server = Server([{'/get': {'method': 'GET', 'headers': {'X-Method': '(GET|HEAD)'}}}])
        
        server.app.testing = True
        client = server.app.test_client()

        response = client.get('/get', headers={'X-Method': 'GET'})

        self.assertEqual(200, response.status_code)

        response = client.get('/get', headers={'X-Method': 'Invalid'})

        self.assertEqual(409, response.status_code)

    def test_async_request(self):
        self.server = Server([
            {
                '/testing': {
                    'body': {
                        'key': 'value'
                    },
                    'async': True,
                    'actions': [
                        {
                            'sleep': {
                                'seconds': 0.5
                            }
                        },
                        {
                            'log': {
                                'message': 'Serving {{ request.path }} with key={{ request.json.key }}'
                            }
                        }
                    ]
                }
            }
        ])

        self.server.app.testing = True
        self.client = self.server.app.test_client()

        _stdout = sys.stdout
        _output = []

        class CapturingStdout(object):
            def write(self, content):
                _output.append(content)

        sys.stdout = CapturingStdout()

        try:
            self._check(200, headers=None, body={'key': 'value'})

            self.assertNotIn('Serving /testing with key=value', ''.join(_output))

            time.sleep(1)

            self.assertIn('Serving /testing with key=value', ''.join(_output))

        finally:
            sys.stdout = _stdout

    def test_metrics(self):
        self.server = Server([
            {
                '/test/post': {
                    'async': True,
                    'actions': [
                        {'sleep': {'seconds': 0.01}},
                        {'log': {}}
                    ]
                },
                '/test/put': {
                    'method': 'PUT',
                    'actions': [
                        {'log': {}},
                        {'execute': {'command': 'echo "Executing command"'}}
                    ]
                }
            }
        ])

        self.server.app.testing = True
        self.client = self.server.app.test_client()

        for _ in range(2):
            response = self.client.post('/test/post',
                                        data=json.dumps({'unused': 1}),
                                        content_type='application/json')

            self.assertEqual(response.status_code, 200)

        for _ in range(3):
            response = self.client.put('/test/put',
                                       data=json.dumps({'unused': 1}),
                                       content_type='application/json')

            self.assertEqual(response.status_code, 200)

        time.sleep(0.1)

        response = self.client.get('/metrics')

        self.assertEqual(response.status_code, 200)

        metrics = response.data.encode('utf-8')

        self.assertIn('flask_http_request_duration_seconds_bucket{le="5.0",method="POST",path="/test/post",status="200"} 2.0', metrics)
        self.assertIn('flask_http_request_duration_seconds_count{method="POST",path="/test/post",status="200"} 2.0', metrics)
        self.assertIn('flask_http_request_duration_seconds_sum{method="POST",path="/test/post",status="200"}', metrics)

        self.assertIn('flask_http_request_duration_seconds_bucket{le="0.5",method="PUT",path="/test/put",status="200"} 3.0', metrics)
        self.assertIn('flask_http_request_duration_seconds_count{method="PUT",path="/test/put",status="200"} 3.0', metrics)
        self.assertIn('flask_http_request_duration_seconds_sum{method="PUT",path="/test/put",status="200"}', metrics)

        self.assertIn('webhook_proxy_actions_count{action_index="0",action_type="sleep",http_method="POST",http_route="/test/post"} 2.0', metrics)
        self.assertIn('webhook_proxy_actions_sum{action_index="0",action_type="sleep",http_method="POST",http_route="/test/post"}', metrics)
        self.assertIn('webhook_proxy_actions_count{action_index="1",action_type="log",http_method="POST",http_route="/test/post"} 2.0', metrics)
        self.assertIn('webhook_proxy_actions_sum{action_index="1",action_type="log",http_method="POST",http_route="/test/post"}', metrics)

        self.assertIn('webhook_proxy_actions_count{action_index="0",action_type="log",http_method="PUT",http_route="/test/put"} 3.0', metrics)
        self.assertIn('webhook_proxy_actions_sum{action_index="0",action_type="log",http_method="PUT",http_route="/test/put"}', metrics)
        self.assertIn('webhook_proxy_actions_count{action_index="1",action_type="execute",http_method="PUT",http_route="/test/put"} 3.0', metrics)
        self.assertIn('webhook_proxy_actions_sum{action_index="1",action_type="execute",http_method="PUT",http_route="/test/put"}', metrics)

