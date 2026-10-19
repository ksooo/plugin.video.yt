# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""The exact frame rates of a video, so that Kodi can switch the display before playback.

YouTube gives a format's fps as a whole number: 24 stands for 23.976 as well,
30 for 29.97 and 60 for 59.94. The WebM header of a VP9 format holds the
exact duration of a frame; all formats of a video with the same fps share
it, whatever their codec. The MP4 header of the other codecs holds none.
"""

from concurrent.futures import ThreadPoolExecutor

from . import addon
from . import http

#: The rates assumed where no header tells, as most videos with these fps
#: come from cameras recording at the NTSC rates.
_ESTIMATES = {24: '24000/1001', 30: '30000/1001', 60: '60000/1001'}

#: The EBML id of a track's DefaultDuration, the duration of a frame in nanoseconds.
_DEFAULT_DURATION = b'\x23\xe3\x83'


def of_formats(formats, headers):
    """Return the frame rate of each fps of the formats as a DASH frameRate, e.g. '24000/1001'.

    headers are those to fetch the formats with. One WebM header is read per fps, all at once.
    """
    webm_formats = {}
    for data in formats:
        fps = data.get('fps')
        if fps and fps not in webm_formats and data.get('mimeType', '').startswith('video/webm'):
            webm_formats[fps] = data
    with ThreadPoolExecutor(max_workers=max(1, len(webm_formats))) as pool:
        rates = dict(zip(webm_formats,
                         pool.map(lambda data: _read(data, headers), webm_formats.values())))
    for data in formats:
        fps = data.get('fps')
        if fps and not rates.get(fps):
            rates[fps] = _ESTIMATES.get(fps, str(fps))
            addon.log_warning('no WebM header tells the frame rate of {} fps, assuming {:.3f}'
                              .format(fps, _fps(rates[fps])))
    return rates


def _fps(frame_rate):
    """Return the frames per second of a DASH frameRate such as '24000/1001'."""
    numerator, _, denominator = frame_rate.partition('/')
    return int(numerator) / int(denominator or 1)


def _read(data, headers):
    """Return the frame rate in the WebM header of the format, None if it tells none."""
    init_range = data.get('initRange')
    if not init_range:
        return None
    try:
        header = http.get(data['url'], dict(
            headers, Range='bytes={start}-{end}'.format(**init_range)))
    except http.RequestError as error:
        addon.log_error(str(error))
        return None
    nanoseconds = _default_duration(header or b'')
    return _frame_rate(nanoseconds) if nanoseconds else None


def _default_duration(header):
    """Return the DefaultDuration in the WebM header, None if there is none."""
    start = header.find(_DEFAULT_DURATION)
    if start < 0:
        return None
    start += len(_DEFAULT_DURATION)
    # The size is an EBML variable length integer: its leading zero bits tell
    # how many more bytes it takes.
    first = header[start]
    length = 1
    while length < 8 and not first & (0x80 >> (length - 1)):
        length += 1
    size = int.from_bytes(bytes([first & (0xff >> length)]) + header[start + 1:start + length],
                          'big')
    start += length
    return int.from_bytes(header[start:start + size], 'big') or None


def _frame_rate(nanoseconds):
    """Return the rate of frames lasting that long as a DASH frameRate."""
    rate = 1e9 / nanoseconds
    if abs(rate - round(rate)) < 0.01:
        return str(round(rate))
    ntsc = round(rate * 1.001)
    if abs(rate - ntsc / 1.001) < 0.01:
        return '{}/1001'.format(ntsc * 1000)
    return '{}/1000'.format(round(rate * 1000))
