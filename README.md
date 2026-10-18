# YouTube

A Kodi video add-on for YouTube: subscriptions, recommendations, trending, search and watch history
as folders in Kodi's video window.

![icon](resources/icon.png)

## Folders

The top level offers:

* **Subscriptions**, when signed in: **All subscriptions**, the 100 newest videos of all subscribed
  channels together, then the channels, below each channel its 100 newest videos - those of the
  channel's **Videos** tab on YouTube, so neither shorts nor live recordings.
* **Recommendations**, when signed in: YouTube's recommendations for you, in the shelves of the
  YouTube app's home - "Recommended", "Recently uploaded", topics and so on.
* **Trending**: **All trends**, then YouTube's categories such as music, gaming or sports, each
  with its 100 most popular videos in the region set in Kodi. Categories YouTube keeps no chart
  for in the region are left out.
* **Live**: the live streams YouTube features now, the upcoming ones and those just ended, about
  15 each, in the region and language set in Kodi. Upcoming ones play from their start on.
* **Search**: a new search, and the 20 recent searches to run again or delete. YouTube searches
  by relevance, in the region and language set in Kodi.
* **History**, when signed in: the videos watched last on YouTube, the latest first - and in Kodi,
  see [Syncing with YouTube](#syncing-with-youtube).

Trending, live and search work with just the API key, without signing in.

A video's context menu goes to its channel and, when signed in, subscribes to or unsubscribes
from it. A channel's context menu in the subscriptions unsubscribes from it. Any video plays from
`plugin://plugin.video.yt/play/?v=<video id>`.

A video's plot starts with its channel and its numbers of views and likes, as far as YouTube shows
them.

## Playback

Videos play through `inputstream.adaptive`, which picks the resolution the connection and the
display allow. Kodi's own dialogues switch between:

* **Video**: one entry per codec, and HDR as an entry of its own where a video has it. The
  setting **Playback ▸ Video codecs** chooses the codecs offered - VP9 and H.264 by default; AV1
  only plays smoothly where the device decodes it in hardware.
* **Audio**: one entry per audio track - the original and any dubbed one -, plus one for surround
  sound where a video has it.
* **Subtitles**: the subtitles made for the video, and those YouTube recognized from the speech.

Kodi remembers where you stopped and which videos you watched, as for any other video.

## Syncing with YouTube

When signed in, the setting **Playback ▸ Sync playback state with YouTube**, off by default, keeps
Kodi and the account's watch history in step. When it is off, Kodi alone keeps play counts and
resume positions.

* Videos played in Kodi go to the history, along with where they were stopped. Live streams do
  not.
* Videos in the history resume where they were left, wherever they were watched, and count as
  watched from 90 percent on. That holds for the videos watched last - the first page of the
  history; for older ones, what Kodi remembers holds.

From Kodi 23 on, Kodi tells the add-on when a video's play count or resume point changes, and the
add-on passes that on: marking a video watched reports it watched to the end, marking it
unwatched or resetting its resume point removes it from the history, and a resume point Kodi
keeps replaces the one YouTube has, even an earlier one.

Older Kodi versions do not tell, and YouTube only ever moves a position forward. Starting a video
over and stopping it earlier leaves the history, and so the resume point, where it was; a video
watched to the end stays watched until it is deleted from the history on YouTube. Kodi's context
menu entries to mark a video watched or unwatched or to reset its resume point do not reach
YouTube: for a video in the history, the history wins again the next time the folder is listed.

## Requirements

Kodi 21 (Omega) or newer and the add-on `inputstream.adaptive`, which plays the videos. Requiring
version 21 of `inputstream.adaptive` is also what keeps the add-on off older Kodi versions.

## Setup

The add-on brings no access to YouTube of its own. It uses the YouTube Data API with your own
Google Cloud project, which is free:

1. In the [Google Cloud Console](https://console.cloud.google.com/), create a project and enable
   the **YouTube Data API v3** for it.
2. Under **APIs & Services ▸ Credentials**, create an **API key**.
3. Under **Google Auth Platform**, set up the consent screen. On **Audience**, publish the app
   (**In production**). While it stays in **Testing**, Google lets a sign-in expire after seven
   days. Publishing asks for a home page and a privacy policy URL on the **Branding** page. A
   Google Workspace account can choose the user type **Internal** instead and skip all that.
4. Under **Clients**, create an OAuth client of the type **TVs and Limited Input devices**.
5. In the add-on settings, under **Account**, enter the API key, the client ID and the client
   secret, then choose **Sign in**.

Signing in takes two codes, entered one after the other on a phone or computer. The first grants
your own OAuth client access to the account. The second grants it to YouTube's app for Meta Quest,
whose identity the add-on uses for your recommendations and history and to play age-restricted
videos. **Sign out** revokes both.

## Trademark

YouTube and the YouTube logo are trademarks of Google LLC. The logo used as the add-on icon belongs
to its owner and is not covered by the GPL license of this add-on. This add-on is not affiliated
with, endorsed or sponsored by YouTube or Google.
