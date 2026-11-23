# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.account, driven through the settings routes."""

import json
import os
from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase
from tests.support import tokens

from resources.lib import account
from resources.lib import feeds
from resources.lib import http
from resources.lib import oauth


class AccountTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        self.authorized = []
        self.revoked = []
        self.refreshed = []
        # Results of signing in in turn: tokens, None for giving up, or an
        # exception.
        self.authorize_results = [tokens('vr')]
        self.refresh_result = None
        for patcher in (mock.patch.object(oauth, 'authorize', self._authorize),
                        mock.patch.object(oauth, 'revoke', self.revoked.append),
                        mock.patch.object(oauth, 'refresh', self._refresh)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _authorize(self, client, show_code, wait):
        self.authorized.append(client)
        show_code('https://www.google.com/device', 'CODE-{}'.format(len(self.authorized)))
        result = self.authorize_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def _refresh(self, client, refresh_token):
        self.refreshed.append((client, refresh_token))
        if isinstance(self.refresh_result, Exception):
            raise self.refresh_result
        return self.refresh_result

    def stored_tokens(self):
        path = os.path.join(support.PROFILE_DIR, account.TOKENS_FILE)
        if not os.path.exists(path):
            return None
        with open(path, encoding='utf-8') as tokens_file:
            return json.load(tokens_file)


class SignInTest(AccountTestCase):

    def test_youtubes_app_for_meta_quest_is_granted_access(self):
        self.dispatch('signin')
        self.assertEqual(self.authorized, [oauth.YOUTUBE_VR])

    def test_the_dialogue_opens_before_google_is_asked_for_a_code(self):
        self.dispatch('signin')
        self.assertEqual(support.PROGRESS[0], ('create', 'L30016', 'L30114'))

    def test_the_dialogue_then_names_the_code_and_the_purpose(self):
        self.dispatch('signin')
        updates = [event[2] for event in support.PROGRESS if event[0] == 'update']
        self.assertEqual(len(updates), 1)
        self.assertIn('L30111', updates[0])
        self.assertIn('L30113', updates[0])

    def test_success_keeps_the_tokens_and_is_reported(self):
        self.dispatch('signin')
        self.assertEqual(set(self.stored_tokens()), {'vr'})
        self.assertTrue(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30120')])

    def test_giving_up_keeps_nothing(self):
        self.authorize_results = [None]
        self.dispatch('signin')
        self.assertIsNone(self.stored_tokens())
        self.assertFalse(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [])

    def test_a_failure_is_reported(self):
        self.authorize_results = [oauth.OAuthError('access_denied')]
        self.dispatch('signin')
        self.assertIsNone(self.stored_tokens())
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30122')])
        self.assertEqual(self.errors(), ['[plugin.video.yt] sign-in failed: access_denied'])

    def test_a_network_failure_is_reported(self):
        self.authorize_results = [http.RequestError('timed out')]
        self.dispatch('signin')
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30122')])

    def test_the_dialogue_is_always_closed(self):
        self.authorize_results = [oauth.OAuthError('access_denied')]
        self.dispatch('signin')
        self.assertEqual(support.PROGRESS[-1], ('close',))


class SignOutTest(AccountTestCase):

    def test_the_tokens_are_revoked_and_forgotten(self):
        support.store_tokens(vr=tokens('vr'))
        self.dispatch('signout')
        self.assertEqual(self.revoked, ['refresh-vr'])
        self.assertIsNone(self.stored_tokens())
        self.assertFalse(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30121')])

    def test_the_cached_subscriptions_and_likes_go_too(self):
        support.store_tokens(vr=tokens('vr'))
        caches = [os.path.join(support.PROFILE_DIR, file_name)
                  for file_name in (account.SUBSCRIPTIONS_FILE, account.LIKES_FILE)]
        for cache in caches:
            with open(cache, 'w', encoding='utf-8') as cache_file:
                cache_file.write('{}')
        self.dispatch('signout')
        for cache in caches:
            self.assertFalse(os.path.exists(cache))

    def test_the_kept_feeds_of_the_account_go_too(self):
        support.store_tokens(vr=tokens('vr'))
        caches = [os.path.join(support.PROFILE_DIR, file_name)
                  for file_name in (feeds.SHELVES_FILE, feeds.PROGRESS_FILE, feeds.REMOVED_FILE)]
        for cache in caches:
            with open(cache, 'w', encoding='utf-8') as cache_file:
                cache_file.write('{}')
        self.dispatch('signout')
        self.assertEqual([cache for cache in caches if os.path.exists(cache)], [])


class AccessTokenTest(AccountTestCase):

    def test_there_is_none_without_signing_in(self):
        self.assertIsNone(account.access_token(account.VR))

    def test_a_valid_token_is_used_as_it_is(self):
        support.store_tokens(vr=tokens('vr'))
        self.assertEqual(account.access_token(account.VR), 'access-vr')
        self.assertEqual(self.refreshed, [])

    def test_an_expiring_token_is_renewed_with_the_matching_client(self):
        support.store_tokens(vr=tokens('vr', expires_in=30))
        self.refresh_result = dict(tokens('vr'), access_token='access-vr-2')

        self.assertEqual(account.access_token(account.VR), 'access-vr-2')
        self.assertEqual(self.refreshed, [(oauth.YOUTUBE_VR, 'refresh-vr')])
        self.assertEqual(self.stored_tokens()['vr']['access_token'], 'access-vr-2')

    def test_the_token_of_the_users_own_client_is_forgotten_but_not_revoked(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        self.assertEqual(account.access_token(account.VR), 'access-vr')
        self.assertEqual(set(self.stored_tokens()), {'vr'})
        self.assertEqual(self.revoked, [])

    def test_a_refused_renewal_signs_out(self):
        support.store_tokens(vr=tokens('vr', expires_in=-1))
        self.refresh_result = oauth.OAuthError('invalid_grant')

        self.assertIsNone(account.access_token(account.VR))
        self.assertIsNone(self.stored_tokens())
        self.assertFalse(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30123')])

    def test_a_network_failure_keeps_the_sign_in(self):
        support.store_tokens(vr=tokens('vr', expires_in=-1))
        self.refresh_result = http.RequestError('timed out')

        self.assertIsNone(account.access_token(account.VR))
        self.assertIsNotNone(self.stored_tokens())
        self.assertTrue(support.SETTINGS['signed_in'])
