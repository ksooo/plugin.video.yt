# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Directory listings: plugin URLs, list items and handing them to Kodi."""

from urllib.parse import urlencode

import xbmcgui
import xbmcplugin

from . import addon

BASE_URL = 'plugin://plugin.video.yt/'

#: Separator between the breadcrumb parts, matching the one Kodi puts between
#: "Videos", the add-on name and the plugin category.
BREADCRUMB_SEPARATOR = ' / '

CONTENT_VIDEOS = 'videos'

#: From how many percent on a video counts as watched.
WATCHED_PERCENT = 90

#: The counts heading a video's plot: field of dataapi.Video, label ids for
#: many and for one, colour as in other YouTube add-ons.
_COUNTS = (('views', 30500, 30501, 'lightblue'),
           ('likes', 30502, 30503, 'lime'))

_NUMBER_SCALES = ('', 'K', 'M', 'B')


def url(route, **params):
    """Build the plugin URL of a route.

    The parameters are sorted: Kodi keys resume points and play counts by the
    URL, so the same video must always get the very same one. The route ends
    with a slash: Kodi stores the path part of the URL with one, but looks it
    up for listings as it is (CVideoDatabase::GetPlayCounts), so without the
    slash it never finds a video's resume point or play count again.
    """
    if not route:
        return BASE_URL
    if not params:
        return '{}{}/'.format(BASE_URL, route)
    return '{}{}/?{}'.format(BASE_URL, route, urlencode(sorted(params.items())))


def breadcrumb(*parts):
    return BREADCRUMB_SEPARATOR.join(parts)


def video_thumbnail(video_id):
    """Return the URL of the video's thumbnail; YouTube keeps it under a fixed one."""
    return 'https://i.ytimg.com/vi/{}/hqdefault.jpg'.format(video_id)


def folder_item(label, route, thumbnail='', context_menu=(), on_top=False, **params):
    """Build the listing tuple of a folder. on_top keeps it first whatever the sorting."""
    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    list_item.setIsFolder(True)
    if on_top:
        list_item.setProperty('SpecialSort', 'top')
    if thumbnail:
        list_item.setArt({'thumb': thumbnail, 'icon': thumbnail})
    else:
        list_item.setArt({'icon': 'DefaultFolder.png'})
    if context_menu:
        list_item.addContextMenuItems(list(context_menu))
    return url(route, **params), list_item, True


def action_item(label, route, icon):
    """Build the listing tuple of an entry that runs an action instead of opening a folder.

    Kodi runs a plugin URL that is neither folder nor playable as a script,
    with no directory pending - unlike a folder, from there the action can
    send Kodi elsewhere with Container.Update.
    """
    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    list_item.setIsFolder(False)
    list_item.setArt({'icon': icon})
    return url(route), list_item, False


def search_item(query):
    """Build the listing tuple of a recent search, to run again or delete."""
    return folder_item(query, 'search/results',
                       context_menu=[(addon.localize(30304), 'RunPlugin({})'.format(
                           url('search/forget', q=query)))],
                       q=query)


def channel_item(channel):
    """Build the listing tuple of a subscribed channel, below the subscriptions."""
    return folder_item(channel.title, 'channel', channel.thumbnail,
                       context_menu=[_unsubscribe_entry(30203, channel.channel_id,
                                                        channel.title)],
                       id=channel.channel_id, title=channel.title, parent='subscriptions')


def video_item(video, subscribed, liked, link_channel, percent_watched=None):
    """Build the listing tuple of a playable video.

    subscribed tells whether the account subscribed to the video's channel,
    liked whether it liked the video, both None if nobody is signed in.
    link_channel tells whether to offer going to the channel. percent_watched,
    how far the account watched the video on YouTube, overrides the play count
    and resume point Kodi keeps; None leaves those to Kodi.
    """
    context_menu = []
    if link_channel and subscribed is not None:
        context_menu.append((addon.localize(30206).format(video.channel_title),
                             'RunPlugin({})'.format(url('channel/menu', channel=video.channel_id,
                                                        title=video.channel_title,
                                                        subscribed=int(subscribed)))))
    elif link_channel:
        context_menu.append((addon.localize(30204).format(video.channel_title),
                             'Container.Update({})'.format(url('channel', id=video.channel_id,
                                                               title=video.channel_title))))
    elif subscribed:
        context_menu.append(_unsubscribe_entry(30203, video.channel_id, video.channel_title))
    elif subscribed is not None:
        context_menu.append((addon.localize(30201).format(video.channel_title),
                             'RunPlugin({})'.format(url('subscribe', channel=video.channel_id,
                                                        title=video.channel_title))))
    if liked is not None:
        context_menu.append((addon.localize(30701 if liked else 30700),
                             'RunPlugin({})'.format(url('rate', v=video.video_id,
                                                        rating='none' if liked else 'like'))))

    title = video.title

    list_item = xbmcgui.ListItem(label=title, offscreen=True)
    list_item.addContextMenuItems(context_menu)
    list_item.setIsFolder(False)
    list_item.setProperty('IsPlayable', 'true')
    list_item.setArt({'thumb': video.thumbnail, 'icon': video.thumbnail,
                      'fanart': video.thumbnail})
    if video.published:
        # The date Kodi sorts by and shows as ListItem.Date.
        list_item.setDateTime(video.published)

    info_tag = list_item.getVideoInfoTag()
    info_tag.setMediaType('video')
    info_tag.setTitle(title)
    info_tag.setPlot(_plot(video))
    info_tag.setStudios([video.channel_title])
    info_tag.setPremiered(video.published[:10])
    info_tag.setDuration(video.duration)
    info_tag.setTags(video.tags)
    info_tag.setUniqueIDs({'youtube': video.video_id}, 'youtube')
    if percent_watched is not None:
        watched = percent_watched >= WATCHED_PERCENT
        info_tag.setPlaycount(1 if watched else 0)
        # Kodi only fills in a resume point of its own while the total time is 0.
        info_tag.setResumePoint(0 if watched else video.duration * percent_watched / 100,
                                video.duration)

    return url('play', v=video.video_id), list_item, False


def _plot(video):
    """Return the video's description, headed by its channel and its counts."""
    head = ['[B]{}[/B]'.format(video.channel_title)]
    counts = []
    for field, many_id, one_id, colour in _COUNTS:
        count = getattr(video, field)
        if count:
            label = addon.localize(one_id if count == 1 else many_id).format(_short_number(count))
            counts.append('[COLOR {}][B]{}[/B][/COLOR]'.format(colour, label))
    if counts:
        head.append('  •  '.join(counts))
    head = '[CR]'.join(head)
    return '{}[CR][CR]{}'.format(head, video.description) if video.description else head


def _short_number(number):
    """Return a number rounded to three digits the way YouTube shows it, e.g. 6.34K."""
    value = float('{:.3g}'.format(number))
    scale = 0
    while value >= 1000 and scale < len(_NUMBER_SCALES) - 1:
        value /= 1000
        scale += 1
    return '{:.3g}{}'.format(value, _NUMBER_SCALES[scale])


def _unsubscribe_entry(label_id, channel_id, channel_title):
    return addon.localize(label_id).format(channel_title), 'RunPlugin({})'.format(
        url('unsubscribe', channel=channel_id, title=channel_title))


def finish_folders(handle, items, category, cache=True, by_name=False):
    """Hand a listing of folders over to Kodi.

    Without cache, Kodi fetches the listing anew even when going back to it.
    by_name starts it sorted by name rather than in the order given.
    """
    xbmcplugin.setPluginCategory(handle, category)
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    sort_methods = [xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_LABEL]
    # Kodi starts with the first sort method.
    for sort_method in (sort_methods[::-1] if by_name else sort_methods):
        xbmcplugin.addSortMethod(handle, sort_method)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=cache)


def finish_videos(handle, items, category, by_date=False):
    """Hand a listing of videos over to Kodi; by_date starts it newest first."""
    xbmcplugin.setPluginCategory(handle, category)
    xbmcplugin.setContent(handle, CONTENT_VIDEOS)
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    sort_methods = [xbmcplugin.SORT_METHOD_DATE, xbmcplugin.SORT_METHOD_TITLE,
                    xbmcplugin.SORT_METHOD_DURATION]
    # Kodi starts with the first sort method.
    sort_methods.insert(1 if by_date else 0, xbmcplugin.SORT_METHOD_UNSORTED)
    for sort_method in sort_methods:
        # The date beside each video, as Kodi shows it when sorting by date.
        xbmcplugin.addSortMethod(
            handle, sort_method,
            label2Mask='%J' if sort_method == xbmcplugin.SORT_METHOD_UNSORTED else '')
    xbmcplugin.endOfDirectory(handle)
