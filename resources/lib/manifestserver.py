# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""One-shot HTTP server handing a manifest to inputstream.adaptive.

ISA loads manifests over HTTP only: it requires the HTTP status line of the
response, which a local file or a data: URL does not have. The server listens
on the loopback interface, on a port the system picks, and lives only until
ISA has fetched the manifest.
"""

import time
from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer

_PATH = '/manifest.mpd'


class ManifestServer:
    """Serves one DASH manifest, once."""

    def __init__(self, manifest):
        body = manifest.encode('utf-8')
        self.served = False
        owner = self

        class Handler(BaseHTTPRequestHandler):

            def do_GET(self):
                if self.path != _PATH:
                    self.send_error(404)
                    return
                self.send_response(200)
                # ISA recognises the manifest type only by an exact match.
                self.send_header('Content-Type', 'application/dash+xml')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                owner.served = True

            def log_message(self, *args):
                # The default writes to stderr, which Kodi logs as errors.
                pass

        self._server = HTTPServer(('127.0.0.1', 0), Handler)
        self._server.timeout = 0.5

    @property
    def url(self):
        return 'http://127.0.0.1:{}{}'.format(self._server.server_port, _PATH)

    def serve(self, timeout_seconds, aborted):
        """Wait for the manifest to be fetched, then shut down.

        Gives up after timeout_seconds or once aborted() is true. Returns whether
        the manifest was served.
        """
        deadline = time.monotonic() + timeout_seconds
        try:
            while not self.served and time.monotonic() < deadline and not aborted():
                self._server.handle_request()
        finally:
            self._server.server_close()
        return self.served
