# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.router, driving the add-on as Kodi would."""

# Importing support installs the xbmc* stubs, so it has to come first.
from tests import support
from tests.support import AddonTestCase


class RootTest(AddonTestCase):

    def test_the_top_level_opens(self):
        self.dispatch()
        self.assertTrue(support.PLUGIN_STATE['succeeded'])
        self.assertEqual(self.errors(), [])


class UnknownRouteTest(AddonTestCase):

    def test_kodi_is_told_the_listing_failed(self):
        self.dispatch('nonsense')
        self.assertFalse(support.PLUGIN_STATE['succeeded'])

    def test_the_route_is_logged_as_an_error(self):
        self.dispatch('nonsense')
        self.assertEqual(self.errors(), ['[plugin.video.yt] unknown route: nonsense'])

    def test_a_trailing_slash_makes_no_difference(self):
        self.dispatch('nonsense/')
        self.assertEqual(self.errors(), ['[plugin.video.yt] unknown route: nonsense'])
