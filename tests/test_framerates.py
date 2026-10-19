# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.framerates."""

from unittest import mock

# Importing support installs the xbmc* stubs, so it has to come first.
from tests.support import AddonTestCase
from tests.support import AVC_1080
from tests.support import OPUS
from tests.support import VP9_1080
from tests.support import VP9_720

from resources.lib import framerates
from resources.lib import http

HEADERS = {'User-Agent': 'com.google.android.youtube'}


def webm_header(nanoseconds):
    """The start of a WebM file whose video track has frames lasting that long."""
    return b'\x1a\x45\xdf\xa3\x9f\xae\x01' + b'\x23\xe3\x83\x84' + nanoseconds.to_bytes(4, 'big')


class OfFormatsTest(AddonTestCase):

    def setUp(self):
        super().setUp()
        # The header every request gets: bytes, None for HTTP 404 or an exception to raise.
        self.header = webm_header(41708333)
        self.requests = []
        patcher = mock.patch.object(http, 'get', self._get)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _get(self, url, headers):
        self.requests.append((url, headers))
        if isinstance(self.header, Exception):
            raise self.header
        return self.header

    def test_an_ntsc_rate_is_read_from_the_webm_header(self):
        self.assertEqual(framerates.of_formats([dict(VP9_1080, fps=24)], HEADERS),
                         {24: '24000/1001'})

    def test_a_whole_rate_stays_whole(self):
        self.header = webm_header(16666666)
        self.assertEqual(framerates.of_formats([dict(VP9_1080, fps=60)], HEADERS), {60: '60'})

    def test_one_header_is_read_per_fps_with_the_formats_headers(self):
        self.header = webm_header(33366666)
        rates = framerates.of_formats([dict(VP9_1080, fps=30), dict(VP9_720, fps=30),
                                       dict(AVC_1080, fps=30), OPUS], HEADERS)
        self.assertEqual(rates, {30: '30000/1001'})
        self.assertEqual(self.requests,
                         [(VP9_1080['url'], dict(HEADERS, Range='bytes=0-219'))])

    def test_without_a_webm_format_the_ntsc_rate_is_assumed(self):
        rates = framerates.of_formats([dict(AVC_1080, fps=24), dict(AVC_1080, fps=25)], HEADERS)
        self.assertEqual(rates, {24: '24000/1001', 25: '25'})
        self.assertEqual(self.requests, [])

    def test_an_assumed_rate_is_logged_as_a_warning(self):
        framerates.of_formats([dict(AVC_1080, fps=30)], HEADERS)
        self.assertEqual(self.warnings(), [
            '[plugin.video.yt] no WebM header tells the frame rate of 30 fps, assuming 29.970'])

    def test_a_rate_read_is_not_warned_about(self):
        framerates.of_formats([dict(VP9_1080, fps=24)], HEADERS)
        self.assertEqual(self.warnings(), [])

    def test_a_failed_request_falls_back_to_the_assumed_rate(self):
        self.header = http.RequestError('timed out')
        self.assertEqual(framerates.of_formats([dict(VP9_1080, fps=60)], HEADERS),
                         {60: '60000/1001'})
        self.assertEqual(self.errors(), ['[plugin.video.yt] timed out'])

    def test_a_header_without_frame_duration_falls_back_to_the_assumed_rate(self):
        self.header = b'\x1a\x45\xdf\xa3'
        self.assertEqual(framerates.of_formats([dict(VP9_1080, fps=30)], HEADERS),
                         {30: '30000/1001'})

    def test_formats_without_fps_have_none(self):
        self.assertEqual(framerates.of_formats([VP9_1080, OPUS], HEADERS), {})
