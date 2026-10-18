# -*- coding: utf-8 -*-
#
#  Copyright (C) 2026 ksooo
#  This file is part of plugin.video.yt
#
#  SPDX-License-Identifier: GPL-2.0-or-later
#  See LICENSE.txt for more information.
#
"""Tests for resources.lib.manifest."""

import unittest
import xml.etree.ElementTree as ElementTree

# Importing support installs the xbmc* stubs, so it has to come first.
from tests.support import AAC
from tests.support import AV1_1080
from tests.support import AVC_1080
from tests.support import OPUS
from tests.support import VP9_1080
from tests.support import VP9_720
from tests.support import VP9_HDR_1080
from tests.support import audio_format

from resources.lib import manifest

NS = {'dash': 'urn:mpeg:dash:schema:mpd:2011'}
ALL_VIDEO_CODECS = ('av1', 'vp9', 'avc1')


def build(formats, video_codecs=('vp9', 'avc1'), prefer_hdr=False, captions=()):
    mpd = manifest.build(formats, list(captions), video_codecs, prefer_hdr)
    return None if mpd is None else ElementTree.fromstring(mpd)


def caption(language, name, kind=None):
    track = {'baseUrl': 'https://www.youtube.com/api/timedtext?v=abc&lang={}&fmt=srv3'
                        '&signature=xyz'.format(language),
             'languageCode': language, 'name': {'runs': [{'text': name}]}}
    if kind:
        track['kind'] = kind
    return track


def adaptation_sets(mpd, content_type):
    return [adaptation_set for adaptation_set in mpd.iterfind('dash:Period/dash:AdaptationSet', NS)
            if adaptation_set.get('contentType') == content_type]


def representation_ids(adaptation_set):
    return [representation.get('id')
            for representation in adaptation_set.iterfind('dash:Representation', NS)]


def all_representation_ids(mpd):
    return [representation.get('id')
            for representation in mpd.iterfind('.//dash:Representation', NS)]


class CompletenessTest(unittest.TestCase):

    def test_without_audio_there_is_no_manifest(self):
        self.assertIsNone(build([VP9_1080]))

    def test_without_video_there_is_no_manifest(self):
        self.assertIsNone(build([OPUS]))

    def test_without_an_allowed_video_codec_there_is_no_manifest(self):
        self.assertIsNone(build([AV1_1080, OPUS]))

    def test_the_duration_is_the_longest_stream(self):
        self.assertEqual(build([VP9_1080, OPUS]).get('mediaPresentationDuration'), 'PT212.141S')


class SelectionTest(unittest.TestCase):

    def test_only_the_allowed_video_codecs_are_offered(self):
        mpd = build([AV1_1080, VP9_1080, AVC_1080, OPUS], video_codecs=('vp9',))
        self.assertEqual(all_representation_ids(mpd), ['248', '251'])

    def test_av1_is_offered_when_allowed(self):
        mpd = build([AV1_1080, VP9_1080, OPUS], video_codecs=ALL_VIDEO_CODECS)
        self.assertIn('399', all_representation_ids(mpd))

    def test_formats_without_url_are_skipped(self):
        ciphered = dict(VP9_720)
        del ciphered['url']
        ciphered['signatureCipher'] = 's=abc&sp=sig&url=https%3A%2F%2Fexample'
        self.assertEqual(all_representation_ids(build([VP9_1080, ciphered, OPUS])), ['248', '251'])

    def test_urls_with_an_n_parameter_are_skipped(self):
        throttled = dict(VP9_720, url=VP9_720['url'] + '&n=abcdef')
        self.assertEqual(all_representation_ids(build([VP9_1080, throttled, OPUS])), ['248', '251'])

    def test_formats_without_byte_ranges_are_skipped(self):
        progressive = dict(VP9_720)
        del progressive['indexRange']
        self.assertEqual(all_representation_ids(build([VP9_1080, progressive, OPUS])),
                         ['248', '251'])

    def test_drc_audio_is_skipped(self):
        drc = audio_format(1251, 'audio/webm; codecs="opus"', 140000, isDrc=True)
        self.assertEqual(all_representation_ids(build([VP9_1080, OPUS, drc])), ['248', '251'])

    def test_unknown_codecs_are_skipped(self):
        unknown = audio_format(9999, 'audio/mp4; codecs="mhm1.0x0D"', 400000)
        self.assertEqual(all_representation_ids(build([VP9_1080, OPUS, unknown])), ['248', '251'])


class VideoTest(unittest.TestCase):

    def test_each_codec_gets_a_set_of_its_own(self):
        mpd = build([VP9_1080, VP9_720, AVC_1080, OPUS])
        self.assertEqual([representation_ids(adaptation_set)
                          for adaptation_set in adaptation_sets(mpd, 'video')],
                         [['247', '248'], ['137']])

    def test_the_preferred_codec_comes_first_and_is_the_default(self):
        video = adaptation_sets(build([AVC_1080, VP9_1080, OPUS]), 'video')
        self.assertEqual([adaptation_set.get('name') for adaptation_set in video], ['VP9', 'H.264'])
        self.assertEqual([adaptation_set.get('default') for adaptation_set in video],
                         ['true', None])

    def test_representations_carry_size_and_bandwidth(self):
        representation = build([VP9_1080, OPUS]).find('.//dash:Representation', NS)
        self.assertEqual((representation.get('width'), representation.get('height'),
                          representation.get('bandwidth'), representation.get('codecs')),
                         ('1920', '1080', '2500000', 'vp9'))

    def test_the_url_and_byte_ranges_survive_xml_escaping(self):
        representation = build([VP9_1080, OPUS]).find('.//dash:Representation', NS)
        self.assertEqual(representation.find('dash:BaseURL', NS).text, VP9_1080['url'])
        segment_base = representation.find('dash:SegmentBase', NS)
        self.assertEqual(segment_base.get('indexRange'), '220-1000')
        self.assertEqual(segment_base.find('dash:Initialization', NS).get('range'), '0-219')


class HdrTest(unittest.TestCase):

    def test_hdr_gets_a_set_of_its_own_with_its_transfer_function(self):
        hdr = adaptation_sets(build([VP9_1080, VP9_HDR_1080, OPUS]), 'video')[1]
        self.assertEqual(hdr.get('name'), 'VP9 HDR10')
        prop = hdr.find('dash:SupplementalProperty', NS)
        self.assertEqual((prop.get('schemeIdUri'), prop.get('value')),
                         ('urn:mpeg:mpegB:cicp:TransferCharacteristics', '16'))

    def test_sdr_is_the_default_on_an_sdr_display(self):
        video = adaptation_sets(build([VP9_HDR_1080, VP9_1080, OPUS]), 'video')
        self.assertEqual(video[0].get('name'), 'VP9')
        self.assertEqual(video[0].get('default'), 'true')

    def test_hdr_is_the_default_on_an_hdr_display(self):
        video = adaptation_sets(build([VP9_1080, VP9_HDR_1080, OPUS], prefer_hdr=True), 'video')
        self.assertEqual(video[0].get('name'), 'VP9 HDR10')
        self.assertEqual(video[0].get('default'), 'true')


class SubtitleTest(unittest.TestCase):

    CAPTIONS = [caption('de', 'Deutsch'), caption('en', 'Englisch'),
                caption('en', 'Englisch (automatisch erzeugt)', kind='asr')]

    def subtitles(self):
        return adaptation_sets(build([VP9_1080, OPUS], captions=self.CAPTIONS), 'text')

    def test_every_caption_track_is_offered(self):
        self.assertEqual([(adaptation_set.get('lang'), adaptation_set.get('name'))
                          for adaptation_set in self.subtitles()],
                         [('de', 'Deutsch'), ('en', 'Englisch'),
                          ('en', 'Englisch (automatisch erzeugt)')])

    def test_tracks_are_whole_webvtt_files_with_the_url_on_the_representation(self):
        subtitles = self.subtitles()[0]
        self.assertEqual(subtitles.get('mimeType'), 'text/vtt')
        self.assertIsNone(subtitles.find('dash:BaseURL', NS))
        url = subtitles.find('dash:Representation/dash:BaseURL', NS).text
        self.assertEqual(url, 'https://www.youtube.com/api/timedtext'
                              '?v=abc&lang=de&fmt=vtt&signature=xyz')

    def test_a_recognized_track_comes_as_ttml(self):
        subtitles = self.subtitles()[2]
        self.assertEqual(subtitles.get('mimeType'), 'application/ttml+xml')
        url = subtitles.find('dash:Representation/dash:BaseURL', NS).text
        self.assertIn('&fmt=ttml&', url)

    def test_no_track_is_the_default_kodi_chooses(self):
        self.assertEqual([adaptation_set.get('default') for adaptation_set in self.subtitles()],
                         [None, None, None])

    def test_set_ids_go_on_after_audio(self):
        mpd = build([VP9_1080, OPUS], captions=self.CAPTIONS)
        self.assertEqual([adaptation_set.get('id')
                          for adaptation_set in mpd.iterfind('.//dash:AdaptationSet', NS)],
                         ['0', '1', '2', '3', '4'])

    def test_without_captions_there_are_no_subtitles(self):
        self.assertEqual(adaptation_sets(build([VP9_1080, OPUS]), 'text'), [])


class AudioTest(unittest.TestCase):

    def test_a_track_is_offered_in_the_preferred_codec_only(self):
        audio = adaptation_sets(build([VP9_1080, AAC, OPUS]), 'audio')
        self.assertEqual([adaptation_set.get('name') for adaptation_set in audio], ['Opus'])
        self.assertEqual(audio[0].get('default'), 'true')

    def test_aac_is_used_without_opus(self):
        audio = adaptation_sets(build([VP9_1080, AAC]), 'audio')
        self.assertEqual([adaptation_set.get('name') for adaptation_set in audio], ['AAC'])

    def test_surround_is_offered_next_to_stereo(self):
        ac3 = audio_format(380, 'audio/mp4; codecs="ac-3"', 384000, audioChannels=6)
        eac3 = audio_format(328, 'audio/mp4; codecs="ec-3"', 384000, audioChannels=6)
        audio = adaptation_sets(build([VP9_1080, ac3, AAC, eac3, OPUS]), 'audio')

        self.assertEqual([adaptation_set.get('name') for adaptation_set in audio],
                         ['Opus', 'E-AC-3'])
        self.assertEqual([adaptation_set.get('default') for adaptation_set in audio],
                         ['true', None])
        config = audio[1].find('.//dash:AudioChannelConfiguration', NS)
        self.assertEqual(config.get('value'), '6')

    def test_a_video_with_a_single_track_has_it_as_original(self):
        audio = adaptation_sets(build([VP9_1080, OPUS]), 'audio')[0]
        self.assertEqual(audio.get('original'), 'true')

    def test_each_audio_track_gets_a_set_of_its_own(self):
        original = audio_format(251, 'audio/webm; codecs="opus"', 140000,
                                audioTrack={'id': 'en.4', 'audioIsDefault': True})
        dubbed = audio_format(1251, 'audio/webm; codecs="opus"', 140000,
                              audioTrack={'id': 'de.3', 'audioIsDefault': False})
        described = audio_format(2251, 'audio/webm; codecs="opus"', 140000,
                                 audioTrack={'id': 'en.2', 'audioIsDefault': False})
        dubbed_aac = audio_format(1140, 'audio/mp4; codecs="mp4a.40.2"', 130000,
                                  audioTrack={'id': 'de.3', 'audioIsDefault': False})
        audio = adaptation_sets(build([VP9_1080, dubbed, dubbed_aac, described, original]),
                                'audio')

        self.assertEqual([(adaptation_set.get('lang'), adaptation_set.get('default'),
                           adaptation_set.get('original'), adaptation_set.get('impaired'))
                          for adaptation_set in audio],
                         [('en', 'true', 'true', None),
                          ('de', None, None, None),
                          ('en', None, None, 'true')])

    def test_the_original_is_the_track_tagged_so_not_the_dub_youtube_defaults_to(self):
        dubbed = audio_format(1251, 'audio/webm; codecs="opus"', 140000,
                              audioTrack={'id': 'de-DE.10', 'audioIsDefault': True,
                                          'isAutoDubbed': True})
        dubbed['url'] += '&xtags=acont%3Ddubbed-auto%3Alang%3Dde-DE'
        original = audio_format(251, 'audio/webm; codecs="opus"', 140000,
                                audioTrack={'id': 'en-US.4', 'audioIsDefault': False})
        original['url'] += '&xtags=acont%3Doriginal%3Alang%3Den-US'
        audio = adaptation_sets(build([VP9_1080, dubbed, original]), 'audio')

        self.assertEqual([(adaptation_set.get('lang'), adaptation_set.get('original'))
                          for adaptation_set in audio],
                         [('en-US', 'true'), ('de-DE', None)])
