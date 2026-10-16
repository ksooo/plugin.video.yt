# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.oauth."""

import time
import unittest
from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
import tests.support  # noqa: F401

from resources.lib import http
from resources.lib import oauth

CLIENT = oauth.Client('id.apps.googleusercontent.com', 'secret')

DEVICE_CODE = {
    'device_code': 'device-1',
    'user_code': 'ABCD-EFGH',
    'verification_url': 'https://www.google.com/device',
    'expires_in': 1800,
    'interval': 5,
}
TOKENS = {'access_token': 'access-1', 'expires_in': 3599, 'refresh_token': 'refresh-1',
          'scope': oauth.SCOPE, 'token_type': 'Bearer'}


class OAuthTestCase(unittest.TestCase):

    def setUp(self):
        self.requests = []
        self.responses = []
        patcher = mock.patch.object(oauth.http, 'post_form', self._post_form)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _post_form(self, url, fields):
        self.requests.append((url, fields))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AuthorizeTest(OAuthTestCase):

    def setUp(self):
        super().setUp()
        self.shown = []
        self.waits = []
        self.give_up_after = None

    def authorize(self):
        return oauth.authorize(CLIENT, lambda url, code: self.shown.append((url, code)),
                               self._wait)

    def _wait(self, seconds):
        self.waits.append(seconds)
        return self.give_up_after is None or len(self.waits) <= self.give_up_after

    def test_the_code_is_shown_and_the_tokens_returned_once_granted(self):
        self.responses = [DEVICE_CODE, {'error': 'authorization_pending'}, TOKENS]
        before = time.time()
        tokens = self.authorize()

        self.assertEqual(self.shown, [('https://www.google.com/device', 'ABCD-EFGH')])
        self.assertEqual((tokens['access_token'], tokens['refresh_token']),
                         ('access-1', 'refresh-1'))
        self.assertGreaterEqual(tokens['expires_at'], before + 3599)

    def test_the_youtube_scope_is_requested(self):
        self.responses = [DEVICE_CODE, TOKENS]
        self.authorize()
        url, fields = self.requests[0]
        self.assertEqual((url, fields['client_id'], fields['scope']),
                         (oauth.DEVICE_CODE_URL, CLIENT.client_id, oauth.SCOPE))

    def test_polling_uses_the_device_code(self):
        self.responses = [DEVICE_CODE, TOKENS]
        self.authorize()
        url, fields = self.requests[1]
        self.assertEqual((url, fields['device_code'], fields['grant_type'],
                          fields['client_secret']),
                         (oauth.TOKEN_URL, 'device-1', oauth.DEVICE_GRANT_TYPE, 'secret'))

    def test_polling_slows_down_when_asked_to(self):
        self.responses = [DEVICE_CODE, {'error': 'slow_down'}, TOKENS]
        self.authorize()
        self.assertEqual(self.waits, [5, 10])

    def test_giving_up_returns_nothing(self):
        self.responses = [DEVICE_CODE, {'error': 'authorization_pending'}]
        self.give_up_after = 1
        self.assertIsNone(self.authorize())

    def test_a_denial_is_an_error(self):
        self.responses = [DEVICE_CODE, {'error': 'access_denied'}]
        with self.assertRaises(oauth.OAuthError) as context:
            self.authorize()
        self.assertEqual(str(context.exception), 'access_denied')

    def test_a_refused_client_is_an_error_before_any_code_is_shown(self):
        self.responses = [{'error': 'invalid_client'}]
        with self.assertRaises(oauth.OAuthError):
            self.authorize()
        self.assertEqual(self.shown, [])


class RefreshTest(OAuthTestCase):

    def test_the_refresh_token_is_kept(self):
        self.responses = [{'access_token': 'access-2', 'expires_in': 3599}]
        tokens = oauth.refresh(CLIENT, 'refresh-1')
        self.assertEqual((tokens['access_token'], tokens['refresh_token']),
                         ('access-2', 'refresh-1'))
        self.assertEqual(self.requests[0][1]['grant_type'], 'refresh_token')

    def test_a_revoked_grant_is_an_error(self):
        self.responses = [{'error': 'invalid_grant'}]
        with self.assertRaises(oauth.OAuthError):
            oauth.refresh(CLIENT, 'refresh-1')


class RevokeTest(OAuthTestCase):

    def test_the_token_is_revoked(self):
        self.responses = [{}]
        oauth.revoke('refresh-1')
        self.assertEqual(self.requests, [(oauth.REVOKE_URL, {'token': 'refresh-1'})])

    def test_failures_are_ignored(self):
        self.responses = [http.RequestError('timed out')]
        oauth.revoke('refresh-1')
