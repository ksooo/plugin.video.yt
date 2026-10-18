# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.rss."""

from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests.support import AddonTestCase

from resources.lib import http
from resources.lib import innertube
from resources.lib import rss


def feed(*entries):
    """A feed of (video id, published) entries, as YouTube sends it."""
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015"'
            ' xmlns="http://www.w3.org/2005/Atom">' + ''.join(
                '<entry><yt:videoId>{}</yt:videoId><published>{}</published></entry>'.format(
                    video_id, published) for video_id, published in entries) +
            '</feed>').encode('utf-8')


class UploadsTest(AddonTestCase):

    def setUp(self):
        super().setUp()
        # Responses by URL: bytes, None for HTTP 404 or an exception to raise.
        self.feeds = {}
        self.requests = []
        patcher = mock.patch.object(http, 'get', self._get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get(self, url, headers):
        self.requests.append((url, headers))
        response = self.feeds[url]
        if isinstance(response, Exception):
            raise response
        return response

    @staticmethod
    def url(channel_id):
        return 'https://www.youtube.com/feeds/videos.xml?playlist_id=UULF' + channel_id[2:]

    def test_the_videos_tab_of_every_channel_is_read_as_the_web_app(self):
        self.feeds = {self.url('UCone'): feed(), self.url('UCtwo'): feed()}
        rss.uploads(['UCone', 'UCtwo'])
        self.assertEqual(sorted(url for url, _ in self.requests),
                         [self.url('UCone'), self.url('UCtwo')])
        self.assertEqual(self.requests[0][1], innertube.WEB.stream_headers)

    def test_the_videos_of_all_channels_come_newest_first(self):
        self.feeds = {
            self.url('UCone'): feed(('a2', '2026-10-17T10:00:00+00:00'),
                                    ('a1', '2026-10-15T10:00:00+00:00')),
            self.url('UCtwo'): feed(('b1', '2026-10-16T10:00:00+00:00')),
        }
        self.assertEqual(rss.uploads(['UCone', 'UCtwo']), ['a2', 'b1', 'a1'])

    def test_a_channel_without_videos_has_none(self):
        self.feeds = {self.url('UCone'): None, self.url('UCtwo'): feed(('b1', '2026-10-16'))}
        self.assertEqual(rss.uploads(['UCone', 'UCtwo']), ['b1'])
        self.assertEqual(self.errors(), [])

    def test_a_failing_feed_is_logged_and_left_out(self):
        self.feeds = {self.url('UCone'): http.RequestError('HTTP 500 from feed'),
                      self.url('UCtwo'): b'<not xml',
                      self.url('UCthree'): feed(('c1', '2026-10-16'))}
        self.assertEqual(rss.uploads(['UCone', 'UCtwo', 'UCthree']), ['c1'])
        self.assertEqual(len(self.errors()), 2)
