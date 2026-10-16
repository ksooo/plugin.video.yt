# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.feeds."""

from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests.support import AddonTestCase

from resources.lib import feeds
from resources.lib import innertube

RECOMMENDED = [innertube.Shelf('Empfohlen', ['v1', 'v2']),
               innertube.Shelf('Kürzlich hochgeladen', ['v3'])]


class FeedsTestCase(AddonTestCase):

    def setUp(self):
        super().setUp()
        self.browsed = []
        self.shelves = {innertube.RECOMMENDATIONS: RECOMMENDED,
                        innertube.HISTORY: [innertube.Shelf('', ['v9', 'v8', 'v9'])]}
        self.progress = {'v9': 40, 'v8': 100}
        for patcher in (mock.patch.object(innertube, 'get_shelves', self._get_shelves),
                        mock.patch.object(innertube, 'get_watch_progress',
                                          self._get_watch_progress)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _get_shelves(self, browse_id, language, region, access_token):
        self.browsed.append((browse_id, language, region, access_token))
        return self.shelves[browse_id]

    def _get_watch_progress(self, language, region, access_token):
        self.browsed.append(('progress', language, region, access_token))
        return dict(self.progress)


class RecommendationsTest(FeedsTestCase):

    def test_the_shelves_are_fetched_in_kodis_language_and_region(self):
        self.assertEqual(feeds.recommendation_shelves('access-vr'), RECOMMENDED)
        self.assertEqual(self.browsed, [('FEwhat_to_watch', 'de', '', 'access-vr')])

    def test_a_shelf_is_opened_as_last_listed(self):
        feeds.recommendation_shelves('access-vr')
        self.shelves[innertube.RECOMMENDATIONS] = [innertube.Shelf('Empfohlen', ['other'])]
        self.assertEqual(feeds.recommendation_shelf('Empfohlen', 'access-vr'), RECOMMENDED[0])
        self.assertEqual(len(self.browsed), 1)

    def test_after_fifteen_minutes_the_shelves_are_fetched_anew(self):
        with mock.patch.object(feeds.time, 'time', return_value=1000000):
            feeds.recommendation_shelves('access-vr')
        self.shelves[innertube.RECOMMENDATIONS] = [innertube.Shelf('Empfohlen', ['other'])]
        with mock.patch.object(feeds.time, 'time', return_value=1000000 + 15 * 60):
            shelf = feeds.recommendation_shelf('Empfohlen', 'access-vr')
        self.assertEqual(shelf.video_ids, ['other'])

    def test_a_shelf_gone_meanwhile_is_none(self):
        feeds.recommendation_shelves('access-vr')
        self.assertIsNone(feeds.recommendation_shelf('Gone', 'access-vr'))


class HistoryTest(FeedsTestCase):

    def test_the_videos_watched_last_come_first_and_once(self):
        self.assertEqual(feeds.history('access-vr'), ['v9', 'v8'])
        self.assertEqual(self.browsed, [('FEhistory', 'de', '', 'access-vr')])


class WatchProgressTest(FeedsTestCase):

    def test_the_progress_is_fetched_in_kodis_language_and_region(self):
        self.assertEqual(feeds.watch_progress('access-vr'), {'v9': 40, 'v8': 100})
        self.assertEqual(self.browsed, [('progress', 'de', '', 'access-vr')])

    def test_the_progress_is_kept_for_five_minutes(self):
        with mock.patch.object(feeds.time, 'time', return_value=1000000):
            feeds.watch_progress('access-vr')
        self.progress = {'v9': 60}
        with mock.patch.object(feeds.time, 'time', return_value=1000000 + 5 * 60 - 1):
            self.assertEqual(feeds.watch_progress('access-vr'), {'v9': 40, 'v8': 100})
        with mock.patch.object(feeds.time, 'time', return_value=1000000 + 5 * 60):
            self.assertEqual(feeds.watch_progress('access-vr'), {'v9': 60})

    def test_watching_in_kodi_shows_before_youtube_has_it(self):
        feeds.watch_progress('access-vr')
        feeds.watched('v9', 70)
        feeds.watched('v7', 20)
        self.assertEqual(feeds.watch_progress('access-vr'), {'v9': 70, 'v8': 100, 'v7': 20})
        self.assertEqual(len(self.browsed), 1)

    def test_like_youtube_a_shorter_watch_keeps_the_furthest_position(self):
        feeds.watch_progress('access-vr')
        feeds.watched('v8', 30)
        self.assertEqual(feeds.watch_progress('access-vr')['v8'], 100)

    def test_without_kept_progress_watching_notes_nothing(self):
        feeds.watched('v9', 70)
        self.assertEqual(feeds.watch_progress('access-vr'), {'v9': 40, 'v8': 100})
