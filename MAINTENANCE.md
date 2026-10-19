# Maintaining the add-on

## Routes

Every listing and every action has a path of its own below the add-on root,
dispatched by `router.py`. Kodi stores resume points and play counts under the
plugin URL of a video, so these URLs are part of the user's data: changing the
URL of a video loses its resume point and play count.

## Listings

Kodi itself keeps resume points and play counts of plugin items, under their
plugin URL, and fills them into later listings (`CVideoDatabase::GetPlayCounts`).
Two things make that work:

* `listing.url()` sorts the parameters, so a video always gets the very same
  URL, the one `.strm` files and favourites use too.
* Every route ends with a slash, as in `play/?v=<id>`. Kodi stores the path
  part of a plugin URL with a trailing slash (`AddPath`), but
  `GetPlayCounts` looks it up as it comes. Without the slash, resuming works
  but listings never show a resume point or play count.
* `listing.video_item()` sets a play count and resume point only for videos
  of the account's watch history, when syncing. Kodi only fills in what the
  item leaves unset - the resume point while its total time is 0.

Channels list the videos of their **Videos** tab on YouTube. YouTube keeps
those in a playlist of its own: `UULF` followed by the channel id without its
`UC`. It holds neither shorts (`UUSH`) nor live recordings (`UULV`), and
does not exist for a channel without a single such video.

"All subscriptions" merges the same playlists of all subscribed channels,
the newest 50 videos of each, eight channels at a time. YouTube's RSS feeds
of the playlists would cost no quota, but they answer unreliably: the same
feed comes at times with its videos, at times as HTTP 404 or 500. The folder
is kept on top of the channels with the `SpecialSort` property.

The likes come from `videos.list` with `myRating=like`, details included.

Every video listing comes in an order of its own, which "Default", the first
sort method, keeps: a channel newest first, the history last watched first,
search, trending, recommendations and likes in YouTube's order. Kodi's
"Date" would not do for the channels: it starts descending for Kodi's own
listings, but for a plugin's always ascending -
`CFileItemList::AddSortMethod` hands over an ascending order, where
`CGUIViewState::AddSortMethod` would pick descending for an unset one.

There is no "next page" entry: a channel, a trending category and the likes
show 100 videos, a search 50, and that's it.

Video titles lose the emojis they start with: Kodi renders a label starting
with one blank. Emojis further on stay, as boxes - skin fonts have no glyphs
for them. `listing._LEADING_EMOJIS` covers the emoji blocks, the symbols and
dingbats used as emojis, and the invisible characters emojis are composed
with; dashes, quotes or the euro sign are not affected.

### Trending

YouTube retired its trending page in 2025; the Data API's `mostPopular`
chart lives on, per video category. `trends.py` lists the region's
assignable categories and asks each for its single most popular video:
YouTube keeps no chart for some of them (`notFound`, `videoChartNotFound`;
in Germany "Education" and "Travel & Events"), and those are left out. That
costs a unit per category, so the outcome is kept for a day in Kodi's temp
directory, per region and language - with the top video's thumbnail, which
pictures the category's folder. "All trends" is the chart without category,
asked for and kept the same way.

A channel's breadcrumb only names the subscriptions when the channel was
opened from there - the `parent` parameter of its URL says so. Gone to from
any other listing, it just names the channel.

### Live

The Data API finds live streams only by `search.list` with an `eventType`,
at 100 units a page. YouTube's own live channel (`innertube.LIVE_CHANNEL`)
shows them for free: its tabs of the streams live now, upcoming and recently
ended, about 15 each, which `innertube.get_live_videos()` browses by their
`params`. Only the web app gets them - the channel is empty for the Quest
app - and it does without signing in. The details come from the Data API as
everywhere else. Should YouTube change the tabs' `params`, the folders turn
up empty: the web page `youtube.com/@live` links to the current ones.

### Search

The search folder follows Kodi's own PVR search: "New search..." and a
folder of the recent searches, nothing between real entries. "New search..."
is neither folder nor playable, so Kodi runs it as an action. That action
sends Kodi to the results with `Container.Update`, so they have a URL of
their own and going back to them does not ask again. From a folder this
would not work: Kodi treats the listing the folder never delivers as failed
and drops the `Container.Update`. Every listing of results moves the query
to the top of the recent searches; finding nothing keeps Kodi where it is,
with a notification.

A search costs 101 quota units, so `search.py` keeps the results for 15
minutes in Kodi's temp directory. Going back to them from a video's channel
or after playback would otherwise search anew. The recent searches are kept
in the profile directory and survive restarts.

### Subscriptions in context menus

Every video offers to subscribe to or unsubscribe from its channel, so every
video listing needs to know the subscriptions. `subscriptions.py` caches them
in the profile directory, as channel id to subscription id - unsubscribing
takes the latter. Listing the subscriptions, subscribing and unsubscribing
update the cache, otherwise it is fetched again after an hour. Signing out
deletes it along with the tokens. After a change the listing is refreshed,
since its context menus were built with the old state - except after
unsubscribing within the channel's own listing: that one is left for the
level above, which Kodi must not cache (`cacheToDisc=False`), so the channel
is gone there.

Where a video offers both going to its channel and changing the
subscription, the two share a submenu named after the channel. Kodi's
`ListItem.addContextMenuItems` takes no submenus, and those of
`kodi.context.item` cannot name the channel, so the entry runs the route
`channel/menu`, which shows the submenu with `Dialog().contextmenu`.

### Likes in context menus

Every video offers to like it or to take the like back, so a video listing
asks for the account's ratings of its videos when signed in. They are not
cached; a listing is refreshed after a change, as for the subscriptions.

## YouTube Data API

`dataapi.py` wraps the calls; each notes its quota cost. A project gets
10,000 units a day. Opening the subscriptions costs 1 unit per 50 channels,
all subscriptions 1 unit per channel and 2 more, opening a channel 4 units,
a category of trending videos 2, the likes 2, a search 101, subscribing or
unsubscribing 50, liking or taking a like back 50. Signed in, a listing of
videos costs 1 unit more per 50 videos for their ratings. Finding the
trending categories costs one unit per category once a day.

A video costs the same whichever parts of it are asked for, so the listings
take its `statistics` too: the numbers of views and likes head its plot,
unless the uploader hides them or they are 0.

A signed-in account's token authorizes every request, for its own data as
for public data. Without a sign-in, the API key does for the public data -
trending, search, channels. The API reports errors as JSON with a `reason`
such as `quotaExceeded`, which the add-on turns into a notification; a used
up quota names the time it starts anew, midnight Pacific Time
(`dataapi.quota_reset()`).

## Signing in

`oauth.py` implements Google's OAuth flow for limited-input devices; signing
in runs it twice (`account.py`):

1. With the user's own OAuth client, for the YouTube Data API.
2. With the OAuth client of YouTube's app for Meta Quest, `oauth.YOUTUBE_VR`.
   YouTube accepts a token only from the app it was issued for, and the
   Quest app is the one that plays age-restricted videos when signed in.
   Should YouTube ever retire that client, signing in fails at step 2 with
   `invalid_client` in the log.

The tokens live in `tokens.json` in the profile directory, never in the
settings. The hidden setting `signed_in` only mirrors whether that file holds
a sign-in, so the settings dialogue can enable the right button. When Google
refuses to renew a token - the user revoked the access, or changed the client
in the settings - the add-on signs out and says so.

Signing out also forgets what is kept of the account besides the tokens: the
subscriptions, and the recommendations and watch progress in Kodi's temp
directory, so another account signing in does not see them.

## Playback

### InnerTube - expect breakage here

The YouTube Data API has no streams. `innertube.py` therefore asks YouTube's
internal API, posing as one of YouTube's apps whose stream URLs need neither a
PO token nor a deciphered `n` parameter - deciphering would take YouTube's
player JavaScript and thus a JavaScript runtime. The clients are asked in the
order of `PLAYER_CLIENTS`:

1. `ANDROID` with the params `2AMB`. Offers every format and every audio
   track, dubbed ones included. Without the params it needs a PO token.
2. `ANDROID_VR`, the app for Meta Quest. Offers the original audio track only,
   but is asked signed in when there is a sign-in, which unlocks
   age-restricted videos.

When YouTube refuses a client, typically with "Sign in to confirm you're not a
bot", the request is repeated once with the visitor id from the refusal, which
passes the check. The segments are then fetched with the headers of the
client that was served; the log names it.

The web and TV clients are no use: their stream URLs need deciphering, and
without signing in the TV client gets no streams at all.

None of this is documented or promised. Signs of trouble and what to do:

* Every video fails with a reason such as "update the app" - YouTube retired
  the app version. Update the version in the context and user agent of the
  client to a current release.
* All stream URLs carry an `n` parameter - `manifest.py` drops them, so every
  video fails with "This video cannot be played". The client no longer gets
  plain URLs and has to be replaced.
* Segments fail with HTTP 403 in the ISA log - YouTube started checking more
  of the client identity on stream requests than `stream_headers` sends.

### Recommendations and history

The Data API has neither, so `innertube.get_shelves()` browses the
account's feeds `FEwhat_to_watch` and `FEhistory`, as the Quest app with its
token - the TV app's sign-in that other clients use is not needed. Only the
video ids and the shelf titles are taken from the response, the
`compactVideoRenderer` items of the shelves; the videos' details come from
the Data API like everywhere else. If YouTube changes the layout of these
responses, the folders turn up empty.

The recommendations change with every request and their shelves have no id.
`feeds.py` keeps the shelves last listed for 15 minutes in Kodi's temp
directory and opens a shelf by its title from there, so it shows what the
list promised.

### Syncing with the watch history

With the setting `sync_playback` on and a sign-in, the add-on syncs both ways:

* **Kodi to YouTube**: the plugin call that resolved a video stays alive
  while Kodi plays it (`watchtime.py`) and reports to the URLs of the player
  response's `playbackTracking`, as the apps do: `videostatsPlaybackUrl`
  once at the start, `videostatsWatchtimeUrl` every 10 seconds and when
  playback stops, with the time watched since the last report (`st`, `et`)
  and the player's `state`. The URLs belong to the account only in a
  signed-in player response, and only the Quest app is asked signed in; so
  when `ANDROID` served the video, `innertube.get_signed_in_player()` asks
  the Quest app for them. Live streams are not reported.
* **YouTube to Kodi**: `innertube.get_watch_progress()` takes the
  `percentDurationWatched` of the first page of `FEhistory`; every video
  listing sets play count and resume point of the videos found there, from
  90 percent on as watched. `feeds.py` keeps the progress for 5 minutes;
  when playback in Kodi stops, the position goes into that cache too, since
  YouTube's history takes a moment to show it.

YouTube keeps the furthest position ever reported; reporting a smaller one,
even 0, changes nothing - unless the video was removed from the history
first: "Remove from watch history", a `feedbackEndpoint` in the menu of a
history entry (`innertube.remove_from_history()`). YouTube still delivers a
removed video for a while, so `feeds.py` leaves it out of the history and
the progress for 5 minutes, unless it is watched again.

The service (`service.py`) passes on what Kodi changes of the add-on's
videos otherwise, e.g. from the context menu. Kodi announces that as
`Files.OnPlayCountChanged` and `Files.OnResumePointChanged` from version 23
on; older versions announce changes of library items only, and the service
just waits.

* A play count of 1 or more reports the video watched to the end.
* A play count of 0 removes it from the history.
* A resume point removes the video and reports it watched up to there, so
  an earlier one gets through too.
* A reset resume point removes the video, unless its play count changes
  within 2 seconds before or after: marking a video watched or unwatched,
  and playing it to the end, change both, in either order.

Kodi lists a folder anew right after changing a video in it, before the
history has the change, so the service lists a folder of the add-on anew
once more after the changes it made. It waits for Kodi's busy dialogue to
go first: Kodi drops a refresh asked for while it is still listing.

### The manifest

`manifest.py` builds a DASH manifest from the adaptive formats: YouTube serves
each format as one file, so every Representation is a `SegmentBase` and
inputstream.adaptive (ISA) fetches the segments with `Range` requests, directly
from YouTube.

ISA loads manifests over HTTP only - it requires the status line of an HTTP
response, so neither a file path nor a `data:` URL works, in Kodi 21 and 22
alike. `manifestserver.py` serves the manifest once from the plugin call
itself, on `127.0.0.1` and a port the system picks. Kodi lets a plugin run on
after `setResolvedUrl`, which is what makes this work without a background
service.

Subtitles come from the player response's `captionTracks`: every track made
for the video plus the one recognized from the speech (`kind: asr`); the
machine translations YouTube offers on top are left out. Each is a whole
file, the track's `baseUrl` with `fmt` replaced - the parameter is not part of
the URL's signature. Tracks made for the video come as WebVTT (`fmt=vtt`).
The recognized track comes as TTML (`fmt=ttml`): its WebVTT times every word,
positions every cue and starts each with a line holding a blank, and Kodi
shows nothing of it. ISA wants such a file's URL on the Representation, not
further up, where it would append a slash.

The video codecs offered come from the setting `video_codecs`; the order of
preference among them is fixed in `manifest.VIDEO_CODEC_ORDER`.

Every video Representation gets a `frameRate`, so that Kodi can switch the
display's refresh rate before playback instead of a few seconds into it.
YouTube's `fps` is a whole number, 24 for 23.976 as well; `framerates.py`
reads the exact rate from the WebM header of a VP9 format, one request of a
few hundred bytes per fps, and assumes the NTSC rates otherwise.

Each audio track gets AdaptationSets of its own. The original one is the
track whose URL carries `xtags=acont=original:...`. `audioIsDefault` marks
the track YouTube picks for the language asked for, which for a video
dubbed automatically (`acont=dubbed-auto`) is the dub; it only counts where
a track has no such tag. Automatic dubs get a name of their own, or are left
out with the setting `offer_auto_dubs` switched off.

Kodi-version notes:

* The `name`, `default`, `original` and `impaired` attributes of an
  AdaptationSet are ISA extensions; they label and flag the entries of Kodi's
  stream dialogues.
* The HDR `SupplementalProperty` is read by ISA 22 only. ISA 21 leaves the
  colour information to the decoder, which takes it from the stream.

Live streams skip all this: YouTube's own HLS manifest goes straight to ISA.

## Tests

The add-on logic runs without Kodi. `tests/support.py` installs stand-ins for
the `xbmc*` modules:

```sh
python3 -m unittest discover -s tests -t .
```

Plain `unittest`, nothing beyond the standard library. The CI runs the tests
with Python 3.8, the oldest one a supported Kodi carries (Kodi 21 on Windows),
and 3.14, the newest one.

Out of reach of the tests: the real YouTube responses and everything ISA does
with the manifest.

## Checking a real install

Changes to `.py` files take effect the next time the add-on is opened — Kodi
gives every plugin call a fresh sub-interpreter. Changes to `addon.xml` and the
`strings.po` files need a Kodi restart, a changed `resources/icon.png` also a
cleared texture cache.

Worth a look in `kodi.log` after a change: entries prefixed with
`[plugin.video.yt]` are this add-on's own.
