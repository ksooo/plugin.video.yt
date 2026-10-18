# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""InnerTube, the undocumented API of YouTube's own apps.

Only used for what the YouTube Data API does not offer. For playback the
add-on poses as one of YouTube's apps whose stream URLs need neither a PO
token nor a deciphered n parameter. YouTube retires old app versions, so the
client versions need an update from time to time.
"""

import collections
import random
import string

from . import http

PLAYER_URL = 'https://www.youtube.com/youtubei/v1/player?prettyPrint=false'
BROWSE_URL = 'https://www.youtube.com/youtubei/v1/browse?prettyPrint=false'
FEEDBACK_URL = 'https://www.youtube.com/youtubei/v1/feedback?prettyPrint=false'

#: Browse ids of the account's feeds.
RECOMMENDATIONS = 'FEwhat_to_watch'
HISTORY = 'FEhistory'

#: YouTube's live channel, and the params of its tabs of the streams live now,
#: upcoming and recently ended.
LIVE_CHANNEL = 'UC4R8DWoMoI7CAwX8_LjQHig'
LIVE_NOW = 'EgdsaXZldGFikgEDCKEK'
LIVE_UPCOMING = 'EgdsaXZldGFikgEDCKMK'
LIVE_ENDED = 'EgdsaXZldGFikgEDCKIK'


class Client:
    """The identity of one of YouTube's apps."""

    def __init__(self, client_id, context, user_agent, origin, params=None, account=None):
        self.client_id = client_id
        self.context = context
        self.params = params
        #: Key of the account whose access token the app accepts, see account.py.
        self.account = account
        #: Headers for fetching streams and manifests, matching the identity.
        self.stream_headers = {'User-Agent': user_agent, 'Origin': origin}

    @property
    def name(self):
        return self.context['clientName']

    @property
    def api_headers(self):
        return dict(self.stream_headers, **{
            'X-YouTube-Client-Name': self.client_id,
            'X-YouTube-Client-Version': self.context['clientVersion'],
        })


#: The Android app. Without these params it needs a PO token.
ANDROID = Client(
    '3',
    {
        'clientName': 'ANDROID',
        'clientVersion': '20.10.38',
        'osName': 'Android',
        'osVersion': '15',
        'androidSdkVersion': '32',
        'platform': 'MOBILE',
    },
    'com.google.android.youtube/20.10.38 (Linux; U; Android 15) gzip',
    'https://m.youtube.com',
    params='2AMB')

#: The app for Meta Quest. Offers the original audio track only, but signed in
#: it gets age-restricted videos too.
ANDROID_VR = Client(
    '28',
    {
        'clientName': 'ANDROID_VR',
        'clientVersion': '1.65.10',
        'deviceMake': 'Oculus',
        'deviceModel': 'Quest 3',
        'osName': 'Android',
        'osVersion': '14',
        'androidSdkVersion': '34',
    },
    'com.google.android.apps.youtube.vr.oculus/1.65.10 '
    '(Linux; U; Android 14; eureka-user Build/UP1A.231005.007.A1) gzip',
    'https://www.youtube.com',
    account='vr')

#: The web app, only browsed anonymously: the live channel is empty for the
#: Quest app.
WEB = Client(
    '1',
    {
        'clientName': 'WEB',
        'clientVersion': '2.20261015.01.00',
    },
    'Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0',
    'https://www.youtube.com')

#: Player clients by preference.
PLAYER_CLIENTS = (ANDROID, ANDROID_VR)

#: A player response and the client it was given to.
Player = collections.namedtuple('Player', 'response client')

#: A row of videos of a feed, such as "Recently uploaded" in the recommendations.
Shelf = collections.namedtuple('Shelf', 'title video_ids')

_CPN_ALPHABET = string.ascii_letters + string.digits + '-_'


#: Refusals that a signed-in client may get past, e.g. for age-restricted videos.
_SIGN_IN_STATUSES = frozenset(('LOGIN_REQUIRED', 'AGE_CHECK_REQUIRED',
                               'AGE_VERIFICATION_REQUIRED', 'CONTENT_CHECK_REQUIRED'))


class PlayabilityError(Exception):
    """YouTube refuses to play the video. The message is YouTube's reason, if it gave one.

    sign_in_would_help tells whether YouTube asked for a sign-in while a client
    that accepts one was asked without. starts_at is when an upcoming live
    stream starts, in seconds since the epoch, None for any other video.
    """

    def __init__(self, reason, sign_in_would_help=False, starts_at=None):
        super().__init__(reason)
        self.sign_in_would_help = sign_in_would_help
        self.starts_at = starts_at


def get_player(video_id, language, region, access_token):
    """Return the player response of the first client YouTube serves the video to.

    language and region are ISO codes such as 'de' and 'DE'; YouTube words its
    reasons for refusing a video in that language. Either may be empty.
    access_token(account) returns the token of a signed-in account, or None.
    """
    reasons = []
    asked_for_sign_in = False
    signed_out_client = False
    starts_at = None
    for client in PLAYER_CLIENTS:
        token = access_token(client.account) if client.account else None
        signed_out_client = signed_out_client or (client.account is not None and token is None)
        response = _request_player(client, video_id, language, region, token)
        if not _is_playable(response, video_id):
            # Refusals such as YouTube's bot check carry a visitor id that
            # passes it.
            visitor_data = response.get('responseContext', {}).get('visitorData')
            if visitor_data:
                response = _request_player(client, video_id, language, region, token,
                                           visitor_data)

        if _is_playable(response, video_id):
            return Player(response, client)

        status = response.get('playabilityStatus', {})
        reasons.append(status.get('reason', ''))
        asked_for_sign_in = asked_for_sign_in or status.get('status') in _SIGN_IN_STATUSES
        starts_at = starts_at or _scheduled_start(status)

    raise PlayabilityError(next((reason for reason in reasons if reason), ''),
                           asked_for_sign_in and signed_out_client, starts_at)


def get_shelves(browse_id, language, region, access_token):
    """Return the shelves of one of the signed-in account's feeds, as on the app's home.

    Only the first page is fetched. access_token is the token of the account
    ANDROID_VR accepts.
    """
    shelves = []
    for section in _browse(browse_id, language, region, access_token):
        shelf = _shelf(section)
        if shelf is not None:
            shelves.append(shelf)
    return shelves


def get_watch_progress(language, region, access_token):
    """Return how many percent of each video in the account's watch history were watched.

    Only the first page of the history is fetched; of a video watched more
    than once, the latest viewing counts. access_token is the token of the
    account ANDROID_VR accepts.
    """
    progress = {}
    for video in _history_videos(language, region, access_token):
        percent = _percent_watched(video)
        if percent is not None:
            progress.setdefault(video['videoId'], percent)
    return progress


def remove_from_history(video_id, language, region, access_token):
    """Remove every viewing of the video from the first page of the account's watch history.

    Returns whether the video was there. access_token is the token of the
    account ANDROID_VR accepts.
    """
    viewings = [video for video in _history_videos(language, region, access_token)
                if video['videoId'] == video_id]
    tokens = [token for token in map(_feedback_token, viewings) if token]
    if not tokens:
        return False

    client = ANDROID_VR
    http.post_json(FEEDBACK_URL, {
        'context': {'client': _context(client, language, region)},
        'feedbackTokens': tokens,
    }, dict(client.api_headers, Authorization='Bearer ' + access_token))
    return True


def get_signed_in_player(video_id, language, region, access_token):
    """Return the player response of ANDROID_VR signed in, None if YouTube refuses the video.

    Its playbackTracking holds the URLs that report playing the video to the
    account's watch history; they only work with access_token, the token of
    the account ANDROID_VR accepts.
    """
    response = _request_player(ANDROID_VR, video_id, language, region, access_token)
    return response if _is_playable(response, video_id) else None


def get_live_videos(tab, language, region):
    """Return the ids of the streams on a tab of YouTube's live channel, such as LIVE_NOW.

    Only the first page is fetched.
    """
    response = http.post_json(BROWSE_URL, {
        'context': {'client': _context(WEB, language, region)},
        'browseId': LIVE_CHANNEL,
        'params': tab,
    }, WEB.api_headers)

    video_ids = []
    for video in _renderers(response.get('contents', {}), 'videoRenderer'):
        if 'videoId' in video and video['videoId'] not in video_ids:
            video_ids.append(video['videoId'])
    return video_ids


def new_cpn():
    """Return a new client playback nonce, the id YouTube's apps give each playback."""
    return ''.join(random.choice(_CPN_ALPHABET) for _ in range(16))


def _browse(browse_id, language, region, access_token):
    """Return the sections of the first page of one of the signed-in account's feeds."""
    client = ANDROID_VR
    headers = dict(client.api_headers, Authorization='Bearer ' + access_token)
    response = http.post_json(BROWSE_URL, {
        'context': {'client': _context(client, language, region)},
        'browseId': browse_id,
    }, headers)

    sections = []
    for tab in response.get('contents', {}).get('singleColumnBrowseResultsRenderer', {}).get(
            'tabs', []):
        sections.extend(tab.get('tabRenderer', {}).get('content', {}).get(
            'sectionListRenderer', {}).get('contents', []))
    return sections


def _renderers(node, name):
    """Yield every renderer of the given name, however deep the web app nests it."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == name:
                yield value
            else:
                yield from _renderers(value, name)
    elif isinstance(node, list):
        for value in node:
            yield from _renderers(value, name)


def _history_videos(language, region, access_token):
    """Return the renderers of the videos on the first page of the account's watch history."""
    return [video for section in _browse(HISTORY, language, region, access_token)
            for video in _videos(_section_content(section)[1])]


def _feedback_token(video):
    """Return the token of the menu entry that removes a video from the history, if any."""
    for entry in video.get('menu', {}).get('menuRenderer', {}).get('items', []):
        endpoint = entry.get('menuServiceItemRenderer', {}).get('serviceEndpoint', {})
        token = endpoint.get('feedbackEndpoint', {}).get('feedbackToken')
        if token:
            return token
    return None


def _section_content(section):
    """Return the renderer of a section of a browse response and the section's items."""
    if 'shelfRenderer' in section:
        renderer = section['shelfRenderer']
        content = renderer.get('content', {})
        return renderer, (content.get('verticalListRenderer')
                          or content.get('horizontalListRenderer') or {}).get('items', [])
    if 'itemSectionRenderer' in section:
        renderer = section['itemSectionRenderer']
        return renderer, renderer.get('contents', [])
    return {}, []


def _videos(items):
    """Return the renderers of the videos among the items of a section."""
    return [item['compactVideoRenderer'] for item in items
            if 'videoId' in item.get('compactVideoRenderer', {})]


def _percent_watched(video):
    """Return how many percent of a video were watched, from its renderer; None if not given."""
    for overlay in video.get('thumbnailOverlays', []):
        percent = overlay.get('thumbnailOverlayResumePlaybackRenderer', {}).get(
            'percentDurationWatched')
        if percent is not None:
            return percent
    return None


def _shelf(section):
    """Return the shelf of a section of a browse response, None if it holds no video."""
    renderer, items = _section_content(section)
    video_ids = [video['videoId'] for video in _videos(items)]
    if not video_ids:
        return None
    return Shelf(text(renderer.get('title')), video_ids)


def text(node):
    """Return the text of a text node, which InnerTube gives as simpleText or as runs."""
    if not node:
        return ''
    if 'simpleText' in node:
        return node['simpleText']
    return ''.join(run.get('text', '') for run in node.get('runs', []))


def _context(client, language, region):
    context = dict(client.context)
    if language:
        context['hl'] = language
    if region:
        context['gl'] = region
    return context


def _request_player(client, video_id, language, region, token, visitor_data=None):
    context = _context(client, language, region)
    headers = client.api_headers
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if visitor_data:
        context['visitorData'] = visitor_data
        headers['X-Goog-Visitor-Id'] = visitor_data

    payload = {
        'videoId': video_id,
        'contentCheckOk': True,
        'racyCheckOk': True,
        'context': {'client': context},
    }
    if client.params:
        payload['params'] = client.params
        payload['cpn'] = new_cpn()

    return http.post_json(PLAYER_URL, payload, headers)


def _scheduled_start(status):
    """Return when an upcoming live stream starts, from its playability status, if given."""
    start = status.get('liveStreamability', {}).get('liveStreamabilityRenderer', {}).get(
        'offlineSlate', {}).get('liveStreamOfflineSlateRenderer', {}).get('scheduledStartTime')
    return int(start) if start else None


def _is_playable(response, video_id):
    # For a video it may not show in this app, YouTube answers with another one.
    return (response.get('playabilityStatus', {}).get('status') == 'OK'
            and response.get('videoDetails', {}).get('videoId') == video_id)
