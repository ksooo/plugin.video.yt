# Maintaining the add-on

## Routes

Every listing and every action has a path of its own below the add-on root,
dispatched by `router.py`. Kodi stores resume points and play counts under the
plugin URL of a video, so these URLs are part of the user's data: changing the
URL of a video loses its resume point and play count.

## Tests

The add-on logic runs without Kodi. `tests/support.py` installs stand-ins for
the `xbmc*` modules:

```sh
python3 -m unittest discover -s tests -t .
```

Plain `unittest`, nothing beyond the standard library. The CI runs the tests
with Python 3.8, the oldest one a supported Kodi carries (Kodi 21 on Windows),
and 3.14, the newest one.

## Checking a real install

Changes to `.py` files take effect the next time the add-on is opened — Kodi
gives every plugin call a fresh sub-interpreter. Changes to `addon.xml` and the
`strings.po` files need a Kodi restart, a changed `resources/icon.png` also a
cleared texture cache.

Worth a look in `kodi.log` after a change: entries prefixed with
`[plugin.video.yt]` are this add-on's own.
