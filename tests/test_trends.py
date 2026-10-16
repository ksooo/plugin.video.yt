# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.trends."""

from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase

from resources.lib import addon
from resources.lib import dataapi
from resources.lib import trends

AUTH = dataapi.Auth('access-user', '')

CATEGORIES = [dataapi.Category('10', 'Musik'), dataapi.Category('27', 'Bildung'),
              dataapi.Category('20', 'Gaming'), dataapi.Category('19', 'Reisen & Events')]


def top_video(category_id):
    return dataapi.Video('top-' + category_id, 'Title', '', 'UC1', 'Channel', '', 0,
                         'https://i.ytimg.com/{}.jpg'.format(category_id), [])


class CategoriesTest(AddonTestCase):

    def setUp(self):
        super().setUp()
        support.INFO_LABELS['System.Locale(iso)'] = 'DE'
        self.asked = []
        # How YouTube answers for the chart of each category, None for all.
        self.charts = {None: [top_video('all')], '10': [top_video('10')], '27': 'notFound',
                       '20': [top_video('20')], '19': 'videoChartNotFound'}
        for name, fake in (('video_categories', self._video_categories),
                           ('most_popular', self._most_popular)):
            patcher = mock.patch.object(dataapi, name, fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _video_categories(self, region, language, auth):
        self.asked.append(('categories', region, language))
        return CATEGORIES

    def _most_popular(self, region, category_id, count, auth):
        self.asked.append(('chart', region, category_id, count))
        chart = self.charts[category_id]
        if isinstance(chart, str):
            raise dataapi.DataApiError(chart)
        return chart

    def test_all_come_first_then_the_categories_with_a_chart_in_youtubes_order(self):
        self.assertEqual(trends.categories(AUTH), [
            trends.TrendingCategory('', '', 'https://i.ytimg.com/all.jpg'),
            trends.TrendingCategory('10', 'Musik', 'https://i.ytimg.com/10.jpg'),
            trends.TrendingCategory('20', 'Gaming', 'https://i.ytimg.com/20.jpg')])

    def test_each_chart_is_asked_for_a_single_video(self):
        trends.categories(AUTH)
        self.assertEqual(self.asked[0], ('categories', 'DE', 'de'))
        self.assertEqual(self.asked[1:], [('chart', 'DE', None, 1)]
                         + [('chart', 'DE', category.category_id, 1) for category in CATEGORIES])

    def test_an_empty_chart_is_none(self):
        self.charts['10'] = []
        self.assertEqual([category.title for category in trends.categories(AUTH)],
                         ['', 'Gaming'])

    def test_other_refusals_are_passed_on(self):
        self.charts['10'] = 'quotaExceeded'
        with self.assertRaises(dataapi.DataApiError):
            trends.categories(AUTH)

    def test_the_categories_are_kept_for_a_day(self):
        with mock.patch.object(addon.time, 'time', return_value=1000000):
            trends.categories(AUTH)
            trends.categories(AUTH)
        self.assertEqual(len([ask for ask in self.asked if ask[0] == 'categories']), 1)

        with mock.patch.object(addon.time, 'time', return_value=1000000 + 24 * 60 * 60):
            trends.categories(AUTH)
        self.assertEqual(len([ask for ask in self.asked if ask[0] == 'categories']), 2)

    def test_another_region_or_language_asks_again(self):
        trends.categories(AUTH)
        support.INFO_LABELS['System.Locale(iso)'] = 'AT'
        trends.categories(AUTH)
        support.LANGUAGE[0] = 'en'
        trends.categories(AUTH)
        self.assertEqual([ask[1:] for ask in self.asked if ask[0] == 'categories'],
                         [('DE', 'de'), ('AT', 'de'), ('AT', 'en')])

    def test_without_a_region_youtubes_default_is_used(self):
        support.INFO_LABELS['System.Locale(iso)'] = ''
        trends.categories(AUTH)
        self.assertEqual(self.asked[0], ('categories', 'US', 'de'))
