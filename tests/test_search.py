# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.search: the recent searches and the results cache."""

from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests.support import AddonTestCase

from resources.lib import addon
from resources.lib import dataapi
from resources.lib import search

AUTH = dataapi.Auth('access-user', '')

VIDEO = dataapi.Video('v1', 'Title', 'About', 'UC1', 'Channel', '2026-10-14T16:00:07Z', 253,
                      'https://i.ytimg.com/v1/max.jpg', ['a'])


class RecentSearchesTest(AddonTestCase):

    def test_there_are_none_at_first(self):
        self.assertEqual(search.recent(), [])

    def test_the_newest_comes_first(self):
        search.remember('first')
        search.remember('second')
        self.assertEqual(search.recent(), ['second', 'first'])

    def test_searching_again_moves_a_query_up_instead_of_repeating_it(self):
        for query in ('first', 'second', 'first'):
            search.remember(query)
        self.assertEqual(search.recent(), ['first', 'second'])

    def test_a_search_can_be_forgotten(self):
        for query in ('first', 'second', 'third'):
            search.remember(query)
        search.forget('second')
        self.assertEqual(search.recent(), ['third', 'first'])

    def test_the_oldest_beyond_twenty_is_dropped(self):
        for number in range(21):
            search.remember('query {}'.format(number))
        recent = search.recent()
        self.assertEqual(len(recent), 20)
        self.assertEqual((recent[0], recent[-1]), ('query 20', 'query 1'))


class ResultsTest(AddonTestCase):

    def setUp(self):
        super().setUp()
        self.searches = []
        patcher = mock.patch.object(dataapi, 'search', self._search)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _search(self, query, region, language, count, auth):
        self.searches.append((query, region, language, count))
        return [VIDEO]

    def results(self, query='kodi', region='DE'):
        return search.results(query, region, 'de', 50, AUTH)

    def test_the_first_search_asks_youtube(self):
        self.assertEqual(self.results(), [VIDEO])
        self.assertEqual(self.searches, [('kodi', 'DE', 'de', 50)])

    def test_searching_again_soon_takes_the_cached_results(self):
        self.results()
        self.assertEqual(self.results(), [VIDEO])
        self.assertEqual(len(self.searches), 1)

    def test_another_query_or_region_asks_youtube_again(self):
        self.results()
        self.results(query='other')
        self.results(region='AT')
        self.assertEqual(len(self.searches), 3)

    def test_results_older_than_fifteen_minutes_are_searched_anew(self):
        with mock.patch.object(addon.time, 'time', return_value=1000000):
            self.results()
        with mock.patch.object(addon.time, 'time', return_value=1000000 + 15 * 60):
            self.results()
        self.assertEqual(len(self.searches), 2)
