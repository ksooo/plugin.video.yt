# Maintaining the add-on

## Routes

Every listing and every action has a path of its own below the add-on root,
dispatched by `router.py`. Kodi stores resume points and play counts under the
plugin URL of a video, so these URLs are part of the user's data: changing the
URL of a video loses its resume point and play count.

## Playback

### InnerTube - expect breakage here

The YouTube Data API has no streams. `innertube.py` therefore asks YouTube's
internal API, posing as one of YouTube's apps whose stream URLs need neither a
PO token nor a deciphered `n` parameter - deciphering would take YouTube's
player JavaScript and thus a JavaScript runtime. The clients are asked in the
order of `PLAYER_CLIENTS`:

1. `ANDROID` with the params `2AMB`. Offers every format and every audio
   track, dubbed ones included. Without the params it needs a PO token.
2. `ANDROID_VR`, the app for Meta Quest. Offers the original audio track only.

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
