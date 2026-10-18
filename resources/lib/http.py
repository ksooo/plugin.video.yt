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
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

TIMEOUT_SECONDS = 15


class RequestError(Exception):
    """A request failed: no connection, a timeout, an error status or no JSON."""


def post_json(url, payload, headers):
    """POST payload as JSON and return the decoded JSON response."""
    request = Request(url, data=json.dumps(payload).encode('utf-8'), method='POST',
                      headers=dict(headers, **{'Content-Type': 'application/json'}))
    return _fetch_json(request, url, error_body=False)


def request_json(method, url, headers, payload=None):
    """Send a request, with payload as JSON if given, and return the decoded JSON response.

    An error status with a JSON body is returned as well: the YouTube Data API
    reports its errors that way. A response without a body yields {}.
    """
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers = dict(headers, **{'Content-Type': 'application/json'})
    return _fetch_json(Request(url, data=data, method=method, headers=headers), url,
                       error_body=True)


def post_form(url, fields):
    """POST form fields and return the decoded JSON response.

    An error status with a JSON body is returned as well: OAuth reports its
    errors that way.
    """
    request = Request(url, data=urlencode(fields).encode('utf-8'), method='POST',
                      headers={'Content-Type': 'application/x-www-form-urlencoded'})
    return _fetch_json(request, url, error_body=True)


def get(url, headers):
    """GET the URL and return the body, None if there is nothing at it (HTTP 404)."""
    try:
        with urlopen(Request(url, headers=headers), timeout=TIMEOUT_SECONDS) as response:
            return response.read()
    except HTTPError as error:
        if error.code == 404:
            return None
        raise RequestError('HTTP {} from {}'.format(error.code, url)) from error
    except (URLError, OSError) as error:
        raise RequestError('{} from {}'.format(error, url)) from error


def _fetch_json(request, url, error_body):
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read()
            return json.loads(body.decode('utf-8')) if body else {}
    except HTTPError as error:
        if error_body:
            try:
                return json.loads(error.read().decode('utf-8'))
            except ValueError:
                pass
        raise RequestError('HTTP {} from {}'.format(error.code, url)) from error
    except (URLError, OSError, ValueError) as error:
        raise RequestError('{} from {}'.format(error, url)) from error
