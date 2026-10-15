# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""HTTP requests, built on the standard library."""

import json
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

TIMEOUT_SECONDS = 15


class RequestError(Exception):
    """A request failed: no connection, a timeout, an error status or no JSON."""


def post_json(url, payload, headers):
    """POST payload as JSON and return the decoded JSON response."""
    request = Request(url, data=json.dumps(payload).encode('utf-8'), method='POST',
                      headers=dict(headers, **{'Content-Type': 'application/json'}))
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as error:
        raise RequestError('HTTP {} from {}'.format(error.code, url)) from error
    except (URLError, OSError, ValueError) as error:
        raise RequestError('{} from {}'.format(error, url)) from error
