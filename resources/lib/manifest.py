# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""DASH manifest built from the adaptive formats of a player response.

YouTube serves every format as one file, so each Representation is a
SegmentBase with the byte ranges of its init segment and its index, and
inputstream.adaptive fetches the segments with Range requests.

Each AdaptationSet is an entry in Kodi's stream selection dialogues, so each
has to be a real choice. Video gets one per codec and transfer function. Audio
gets one per audio track in stereo and one in surround, each in the most
preferred codec available: Kodi decodes every audio codec in software, so a
second codec for the same sound would be no choice.

Subtitles get one per caption track as a whole file: the tracks made for the
video, and the one YouTube recognized from the speech. YouTube's machine
translations of them are left out.
"""

import re
import xml.etree.ElementTree as ElementTree
from urllib.parse import parse_qs
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlsplit

from . import innertube

#: Codec families by preference. The first one available is the default.
VIDEO_CODEC_ORDER = ('av1', 'vp9', 'avc1')
AUDIO_CODEC_ORDER = ('opus', 'mp4a', 'ec-3', 'ac-3')

_CODEC_FAMILIES = {
    'av01': 'av1',
    'vp9': 'vp9',
    'vp09': 'vp9',
    'avc1': 'avc1',
    'opus': 'opus',
    'mp4a': 'mp4a',
    'ec-3': 'ec-3',
    'ac-3': 'ac-3',
}

_CODEC_NAMES = {
    'av1': 'AV1',
    'vp9': 'VP9',
    'avc1': 'H.264',
    'opus': 'Opus',
    'mp4a': 'AAC',
    'ec-3': 'E-AC-3',
    'ac-3': 'AC-3',
}

#: colorInfo.transferCharacteristics of HDR formats: CICP code point and name.
_HDR_TRANSFERS = {
    'COLOR_TRANSFER_CHARACTERISTICS_SMPTEST2084': (16, 'HDR10'),
    'COLOR_TRANSFER_CHARACTERISTICS_ARIB_STD_B67': (18, 'HLG'),
}

#: Role part of audioTrack.id ('<language>.<role>') for an audio description.
_ROLE_DESCRIPTION = '2'

_MIME_TYPE = re.compile(r'^(?P<mime>[\w-]+/[\w.+-]+);\s*codecs="(?P<codecs>[^"]+)"$')


def build(formats, captions, video_codecs, prefer_hdr, auto_dub_name):
    """Return the MPD for the adaptive formats, or None without video or audio.

    captions are the captionTracks of the player response. video_codecs is the
    collection of video codec families allowed, prefer_hdr makes an HDR
    AdaptationSet the default one when there is one. auto_dub_name names the
    audio tracks YouTube dubbed automatically; None leaves them out.
    """
    video_sets = {}
    audio_sets = {}
    for data in formats:
        parsed = _parse(data)
        if parsed is None:
            continue

        mime, family = parsed
        if mime.startswith('video/') and family in video_codecs:
            transfer = _HDR_TRANSFERS.get(data.get('colorInfo', {}).get('transferCharacteristics'))
            video_sets.setdefault((mime, family, transfer), []).append(data)
        elif mime.startswith('audio/') and family in AUDIO_CODEC_ORDER and not data.get('isDrc'):
            if auto_dub_name is None and _is_auto_dub(data):
                continue
            track_id = data.get('audioTrack', {}).get('id', '')
            surround = int(data.get('audioChannels', 2)) > 2
            audio_sets.setdefault((mime, family, track_id, surround), []).append(data)

    if not video_sets or not audio_sets:
        return None

    audio_sets = _keep_preferred_codec(audio_sets)

    def video_rank(key):
        _, family, transfer = key
        return (transfer is not None) != prefer_hdr, VIDEO_CODEC_ORDER.index(family)

    def audio_rank(key):
        _, family, _, surround = key
        return not _is_original(audio_sets[key][0]), surround, AUDIO_CODEC_ORDER.index(family)

    mpd = ElementTree.Element('MPD', {
        'xmlns': 'urn:mpeg:dash:schema:mpd:2011',
        'profiles': 'urn:mpeg:dash:profile:isoff-on-demand:2011',
        'type': 'static',
        'minBufferTime': 'PT1.5S',
        'mediaPresentationDuration': 'PT{:.3f}S'.format(_duration_seconds(formats)),
    })
    period = ElementTree.SubElement(mpd, 'Period')

    for index, key in enumerate(sorted(video_sets, key=video_rank)):
        _add_video_set(period, index, key, video_sets[key], index == 0)

    for index, key in enumerate(sorted(audio_sets, key=audio_rank), start=len(video_sets)):
        _add_audio_set(period, index, key, audio_sets[key], index == len(video_sets),
                       auto_dub_name)

    for index, track in enumerate(captions, start=len(video_sets) + len(audio_sets)):
        _add_subtitle_set(period, index, track)

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(mpd, encoding='unicode')


def _parse(data):
    """Return mime type and codec family of a usable format, else None."""
    url = data.get('url')
    if not url or 'initRange' not in data or 'indexRange' not in data:
        return None

    # An n parameter has to be deciphered with YouTube's player JavaScript,
    # otherwise the stream is throttled or rejected.
    if 'n' in parse_qs(urlsplit(url).query):
        return None

    match = _MIME_TYPE.match(data.get('mimeType', ''))
    if match is None:
        return None

    family = _CODEC_FAMILIES.get(match.group('codecs').split('.')[0])
    if family is None:
        return None

    return match.group('mime'), family


def _keep_preferred_codec(audio_sets):
    """Reduce the audio sets to one per track and channel layout."""
    preferred = {}
    for key in audio_sets:
        _, family, track_id, surround = key
        current = preferred.get((track_id, surround))
        if (current is None
                or AUDIO_CODEC_ORDER.index(family) < AUDIO_CODEC_ORDER.index(current[1])):
            preferred[(track_id, surround)] = key
    return {key: audio_sets[key] for key in preferred.values()}


def _is_original(data):
    """Whether the audio format belongs to the original audio track."""
    track = data.get('audioTrack')
    if track is None:
        return True
    content = _xtags(data).get('acont')
    return content == 'original' if content else bool(track.get('audioIsDefault'))


def _is_auto_dub(data):
    """Whether the audio format belongs to a track YouTube dubbed automatically."""
    return _xtags(data).get('acont') == 'dubbed-auto'


def _xtags(data):
    """Return the tags of a format's URL, e.g. {'acont': 'original', 'lang': 'en-US'}."""
    xtags = dict(parse_qsl(urlsplit(data.get('url', '')).query)).get('xtags', '')
    return dict(tag.partition('=')[::2] for tag in xtags.split(':') if tag)


def _duration_seconds(formats):
    return max(int(data.get('approxDurationMs', 0)) for data in formats) / 1000


def _add_video_set(period, index, key, formats, is_default):
    mime, family, transfer = key
    name = _CODEC_NAMES[family] if transfer is None else '{} {}'.format(_CODEC_NAMES[family],
                                                                        transfer[1])
    adaptation_set = _add_adaptation_set(period, index, 'video', mime, name, is_default)
    if transfer is not None:
        ElementTree.SubElement(adaptation_set, 'SupplementalProperty', {
            'schemeIdUri': 'urn:mpeg:mpegB:cicp:TransferCharacteristics',
            'value': str(transfer[0]),
        })

    for data in sorted(formats, key=lambda data: (data.get('height', 0), data['bitrate'])):
        representation = _add_representation(adaptation_set, data)
        representation.set('width', str(data['width']))
        representation.set('height', str(data['height']))
        _add_segment_base(representation, data)


def _add_audio_set(period, index, key, formats, is_default, auto_dub_name):
    mime, family, track_id, _ = key
    name = auto_dub_name if _is_auto_dub(formats[0]) else _CODEC_NAMES[family]
    adaptation_set = _add_adaptation_set(period, index, 'audio', mime, name, is_default)
    if track_id:
        language, _, role = track_id.partition('.')
        adaptation_set.set('lang', language)
        if role == _ROLE_DESCRIPTION:
            adaptation_set.set('impaired', 'true')
    if _is_original(formats[0]):
        adaptation_set.set('original', 'true')

    for data in sorted(formats, key=lambda data: data['bitrate']):
        representation = _add_representation(adaptation_set, data)
        representation.set('audioSamplingRate', data.get('audioSampleRate', '48000'))
        ElementTree.SubElement(representation, 'AudioChannelConfiguration', {
            'schemeIdUri': 'urn:mpeg:dash:23003:3:audio_channel_configuration:2011',
            'value': str(data.get('audioChannels', 2)),
        })
        _add_segment_base(representation, data)


def _add_subtitle_set(period, index, track):
    # YouTube's WebVTT of a recognized track times every word, positions the
    # cues and starts each with a line holding a blank, which hides the text
    # in Kodi. Its TTML of the same track is plain lines.
    mime, caption_format = (('application/ttml+xml', 'ttml') if track.get('kind') == 'asr'
                            else ('text/vtt', 'vtt'))
    adaptation_set = _add_adaptation_set(period, index, 'text', mime,
                                         innertube.text(track.get('name')), is_default=False)
    adaptation_set.set('lang', track['languageCode'])
    representation = ElementTree.SubElement(adaptation_set, 'Representation',
                                            {'id': 'subtitles-{}'.format(index)})
    # ISA takes a whole file only from a Representation's BaseURL; one further
    # up would get a slash appended.
    ElementTree.SubElement(representation, 'BaseURL').text = _caption_url(track['baseUrl'],
                                                                          caption_format)


def _caption_url(url, caption_format):
    """Ask for the format instead of the one named in the URL; fmt is not signed."""
    parts = urlsplit(url)
    params = dict(parse_qsl(parts.query), fmt=caption_format)
    return parts._replace(query=urlencode(params)).geturl()


def _add_adaptation_set(period, index, content_type, mime, name, is_default):
    """Add an AdaptationSet. name, default, original and impaired are ISA extensions."""
    adaptation_set = ElementTree.SubElement(period, 'AdaptationSet', {
        'id': str(index),
        'contentType': content_type,
        'mimeType': mime,
        'subsegmentAlignment': 'true',
        'name': name,
    })
    if is_default:
        adaptation_set.set('default', 'true')
    return adaptation_set


def _add_representation(adaptation_set, data):
    return ElementTree.SubElement(adaptation_set, 'Representation', {
        'id': str(data['itag']),
        'codecs': _MIME_TYPE.match(data['mimeType']).group('codecs'),
        'bandwidth': str(data['bitrate']),
    })


def _add_segment_base(representation, data):
    ElementTree.SubElement(representation, 'BaseURL').text = data['url']
    segment_base = ElementTree.SubElement(representation, 'SegmentBase', {
        'indexRange': '{start}-{end}'.format(**data['indexRange']),
    })
    ElementTree.SubElement(segment_base, 'Initialization', {
        'range': '{start}-{end}'.format(**data['initRange']),
    })
