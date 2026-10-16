# YouTube

A Kodi video add-on for YouTube: subscriptions, recommendations, trending, search and watch history
as folders in Kodi's video window.

![icon](resources/icon.png)

## Status

Under construction. Signed in, the add-on lists your subscriptions: below **Subscriptions** the
channels, below each channel its 100 newest videos - those of the channel's **Videos** tab on
YouTube, so neither shorts nor live recordings. A channel's context menu unsubscribes from it, a
video's subscribes to or unsubscribes from its channel. Any video plays from
`plugin://plugin.video.yt/play/?v=<video id>`.

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
whose identity the add-on uses to play age-restricted videos. **Sign out** revokes both.

## Trademark

YouTube and the YouTube logo are trademarks of Google LLC. The logo used as the add-on icon belongs
to its owner and is not covered by the GPL license of this add-on. This add-on is not affiliated
with, endorsed or sponsored by YouTube or Google.
