# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.manifestserver, over real loopback connections."""

import threading
import unittest
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener

# Importing support installs the xbmc* stubs, so it has to come first.
import tests.support  # noqa: F401

from resources.lib.manifestserver import ManifestServer

MANIFEST = '<?xml version="1.0" encoding="UTF-8"?>\n<MPD>ä</MPD>'


class Fetcher(threading.Thread):
    """Fetches a URL the way ISA would, while the server waits."""

    def __init__(self, url, method='GET'):
        super().__init__(daemon=True)
        self.url = url
        self.method = method
        self.status = None
        self.content_type = None
        self.body = None

    def run(self):
        opener = build_opener(ProxyHandler({}))
        try:
            with opener.open(Request(self.url, method=self.method), timeout=5) as response:
                self.status = response.status
                self.content_type = response.headers['Content-Type']
                self.body = response.read()
        except HTTPError as error:
            self.status = error.code
        except URLError:
            # Nobody listening any more; status stays None.
            pass


class ManifestServerTest(unittest.TestCase):

    def test_it_listens_on_the_loopback_interface_only(self):
        server = ManifestServer(MANIFEST)
        self.assertTrue(server.url.startswith('http://127.0.0.1:'))
        server.serve(0, lambda: False)

    def test_the_manifest_is_served_as_dash(self):
        server = ManifestServer(MANIFEST)
        fetcher = Fetcher(server.url)
        fetcher.start()

        self.assertTrue(server.serve(5, lambda: False))
        fetcher.join()
        self.assertEqual((fetcher.status, fetcher.content_type),
                         (200, 'application/dash+xml'))
        self.assertEqual(fetcher.body.decode('utf-8'), MANIFEST)

    def test_it_is_served_once_only(self):
        server = ManifestServer(MANIFEST)
        fetcher = Fetcher(server.url)
        fetcher.start()
        server.serve(5, lambda: False)
        fetcher.join()

        second = Fetcher(server.url)
        second.start()
        second.join()
        self.assertIsNone(second.status)

    def test_other_paths_are_not_found_and_do_not_count(self):
        server = ManifestServer(MANIFEST)
        fetcher = Fetcher(server.url.replace('manifest.mpd', 'other'))
        fetcher.start()

        self.assertFalse(server.serve(1, lambda: False))
        fetcher.join()
        self.assertEqual(fetcher.status, 404)

    def test_kodis_check_before_playback_is_answered_and_does_not_count(self):
        server = ManifestServer(MANIFEST)
        fetcher = Fetcher(server.url + '?mimetype=application%2fdash%2bxml', method='HEAD')
        fetcher.start()

        self.assertFalse(server.serve(1, lambda: False))
        fetcher.join()
        self.assertEqual((fetcher.status, fetcher.content_type, fetcher.body),
                         (200, 'application/dash+xml', b''))

    def test_it_stops_waiting_when_kodi_shuts_down(self):
        self.assertFalse(ManifestServer(MANIFEST).serve(60, lambda: True))
