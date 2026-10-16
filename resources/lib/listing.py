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


def folder_item(label, route, thumbnail='', context_menu=(), **params):
    """Build the listing tuple of a folder."""
    list_item = xbmcgui.ListItem(label=label, offscreen=True)
    list_item.setIsFolder(True)
    if thumbnail:
        list_item.setArt({'thumb': thumbnail, 'icon': thumbnail})
    else:
        list_item.setArt({'icon': 'DefaultFolder.png'})
    if context_menu:
        list_item.addContextMenuItems(list(context_menu))
    return url(route, **params), list_item, True


def channel_item(channel):
    """Build the listing tuple of a subscribed channel."""
    return folder_item(channel.title, 'channel', channel.thumbnail,
                       context_menu=[_unsubscribe_entry(30203, channel.channel_id,
                                                        channel.title)],
                       id=channel.channel_id, title=channel.title)


def video_item(video, subscribed, link_channel):
    """Build the listing tuple of a playable video.

    subscribed tells whether the account subscribed to the video's channel,
    link_channel whether to offer going there.
    """
    context_menu = []
    if link_channel:
        context_menu.append((addon.localize(30204), 'Container.Update({})'.format(
            url('channel', id=video.channel_id, title=video.channel_title))))
    if subscribed:
        context_menu.append(_unsubscribe_entry(30202, video.channel_id, video.channel_title))
    else:
        context_menu.append((addon.localize(30201), 'RunPlugin({})'.format(
            url('subscribe', channel=video.channel_id, title=video.channel_title))))

    list_item = xbmcgui.ListItem(label=video.title, offscreen=True)
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
    info_tag.setTitle(video.title)
    info_tag.setPlot(video.description)
    info_tag.setStudios([video.channel_title])
    info_tag.setPremiered(video.published[:10])
    info_tag.setDuration(video.duration)
    info_tag.setTags(video.tags)
    info_tag.setUniqueIDs({'youtube': video.video_id}, 'youtube')

    return url('play', v=video.video_id), list_item, False


def _unsubscribe_entry(label_id, channel_id, channel_title):
    return addon.localize(label_id), 'RunPlugin({})'.format(
        url('unsubscribe', channel=channel_id, title=channel_title))


def finish_folders(handle, items, category, cache=True):
    """Hand a listing of folders over to Kodi.

    Without cache, Kodi fetches the listing anew even when going back to it.
    """
    xbmcplugin.setPluginCategory(handle, category)
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.addSortMethod(handle, xbmcplugin.SORT_METHOD_LABEL)
    xbmcplugin.endOfDirectory(handle, cacheToDisc=cache)


def finish_videos(handle, items, category):
    """Hand a listing of videos over to Kodi, newest first unless sorted otherwise."""
    xbmcplugin.setPluginCategory(handle, category)
    xbmcplugin.setContent(handle, CONTENT_VIDEOS)
    xbmcplugin.addDirectoryItems(handle, items, len(items))
    for sort_method in (xbmcplugin.SORT_METHOD_UNSORTED, xbmcplugin.SORT_METHOD_DATE,
                        xbmcplugin.SORT_METHOD_TITLE, xbmcplugin.SORT_METHOD_DURATION):
        xbmcplugin.addSortMethod(handle, sort_method)
    xbmcplugin.endOfDirectory(handle)
