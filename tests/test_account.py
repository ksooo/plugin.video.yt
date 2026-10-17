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
        support.SETTINGS.update(client_id='own.apps.googleusercontent.com',
                                client_secret='own-secret')
        self.authorized = []
        self.revoked = []
        self.refreshed = []
        # Results of the sign-in steps in turn: tokens, None for giving up, or
        # an exception.
        self.authorize_results = [tokens('user'), tokens('vr')]
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

    def test_both_accounts_are_granted_in_turn(self):
        self.dispatch('signin')
        self.assertEqual(self.authorized,
                         [oauth.Client('own.apps.googleusercontent.com', 'own-secret'),
                          oauth.YOUTUBE_VR])

    def test_the_dialogue_opens_before_google_is_asked_for_a_code(self):
        self.dispatch('signin')
        self.assertEqual(support.PROGRESS[0], ('create', 'L30110', 'L30114'))

    def test_the_dialogue_then_names_the_code_and_the_purpose(self):
        self.dispatch('signin')
        updates = [event[2] for event in support.PROGRESS if event[0] == 'update']
        self.assertEqual(len(updates), 2)
        self.assertIn('L30111', updates[0])
        self.assertIn('L30112', updates[0])
        self.assertIn('L30113', updates[1])

    def test_success_keeps_the_tokens_and_is_reported(self):
        self.dispatch('signin')
        self.assertEqual(set(self.stored_tokens()), {'user', 'vr'})
        self.assertTrue(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30120')])

    def test_giving_up_revokes_what_was_granted_so_far(self):
        self.authorize_results = [tokens('user'), None]
        self.dispatch('signin')
        self.assertEqual(self.revoked, ['refresh-user'])
        self.assertIsNone(self.stored_tokens())
        self.assertFalse(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [])

    def test_a_failure_revokes_what_was_granted_so_far_and_is_reported(self):
        self.authorize_results = [tokens('user'), oauth.OAuthError('access_denied')]
        self.dispatch('signin')
        self.assertEqual(self.revoked, ['refresh-user'])
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

    def test_all_tokens_are_revoked_and_forgotten(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        self.dispatch('signout')
        self.assertEqual(sorted(self.revoked), ['refresh-user', 'refresh-vr'])
        self.assertIsNone(self.stored_tokens())
        self.assertFalse(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30121')])

    def test_the_cached_subscriptions_go_too(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        cache = os.path.join(support.PROFILE_DIR, account.SUBSCRIPTIONS_FILE)
        with open(cache, 'w', encoding='utf-8') as cache_file:
            cache_file.write('{}')
        self.dispatch('signout')
        self.assertFalse(os.path.exists(cache))

    def test_the_kept_feeds_of_the_account_go_too(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        caches = [os.path.join(support.PROFILE_DIR, file_name)
                  for file_name in (feeds.SHELVES_FILE, feeds.PROGRESS_FILE)]
        for cache in caches:
            with open(cache, 'w', encoding='utf-8') as cache_file:
                cache_file.write('{}')
        self.dispatch('signout')
        self.assertEqual([cache for cache in caches if os.path.exists(cache)], [])


class AccessTokenTest(AccountTestCase):

    def test_there_is_none_without_signing_in(self):
        self.assertIsNone(account.access_token(account.VR))

    def test_a_valid_token_is_used_as_it_is(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr'))
        self.assertEqual(account.access_token(account.VR), 'access-vr')
        self.assertEqual(self.refreshed, [])

    def test_an_expiring_token_is_renewed_with_the_matching_client(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr', expires_in=30))
        self.refresh_result = dict(tokens('vr'), access_token='access-vr-2')

        self.assertEqual(account.access_token(account.VR), 'access-vr-2')
        self.assertEqual(self.refreshed, [(oauth.YOUTUBE_VR, 'refresh-vr')])
        self.assertEqual(self.stored_tokens()['vr']['access_token'], 'access-vr-2')

    def test_the_users_own_client_renews_the_user_token(self):
        support.store_tokens(user=tokens('user', expires_in=-1), vr=tokens('vr'))
        self.refresh_result = tokens('user')
        account.access_token(account.USER)
        self.assertEqual(self.refreshed[0][0],
                         oauth.Client('own.apps.googleusercontent.com', 'own-secret'))

    def test_a_refused_renewal_signs_out(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr', expires_in=-1))
        self.refresh_result = oauth.OAuthError('invalid_grant')

        self.assertIsNone(account.access_token(account.VR))
        self.assertIsNone(self.stored_tokens())
        self.assertFalse(support.SETTINGS['signed_in'])
        self.assertEqual(support.NOTIFICATIONS, [('YouTube', 'L30123')])

    def test_a_network_failure_keeps_the_sign_in(self):
        support.store_tokens(user=tokens('user'), vr=tokens('vr', expires_in=-1))
        self.refresh_result = http.RequestError('timed out')

        self.assertIsNone(account.access_token(account.VR))
        self.assertIsNotNone(self.stored_tokens())
        self.assertTrue(support.SETTINGS['signed_in'])
