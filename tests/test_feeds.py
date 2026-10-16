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
        patcher = mock.patch.object(innertube, 'get_shelves', self._get_shelves)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get_shelves(self, browse_id, language, region, access_token):
        self.browsed.append((browse_id, language, region, access_token))
        return self.shelves[browse_id]


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
