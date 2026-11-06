"""Offline regressions for real Wikimedia media and genuine sound breaks."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fernimoon.commons import allowed_license, pick_media, validate_media_url
from fernimoon.config import Config, PipelineError
from fernimoon.media_sources import collect_priority_media
from fernimoon.script import validate_script
from fernimoon.sound import retime_with_sound
from fernimoon.speech import Word, scene_boundaries
from test_pipeline import config, example_script


def page(*, title="File:Vietnam war military helicopter photo.jpg",
         mime="image/jpeg", licence="Public domain", width=2048, height=1400,
         tags="Photograph of a military helicopter during the Vietnam War"):
    return {"title": title, "imageinfo": [{
        "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/test.jpg",
        "thumburl": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/test.jpg/1280px-test.jpg",
        "width": width, "height": height, "size": 15000, "mime": mime,
        "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test",
        "extmetadata": {
            "LicenseShortName": {"value": licence},
            "LicenseUrl": {"value": "https://creativecommons.org/publicdomain/zero/1.0/"},
            "ImageDescription": {"value": tags},
            "Artist": {"value": "Public archive"},
            "DateTimeOriginal": {"value": "1968"}
        }}]}


class CommonsLicensingTests(unittest.TestCase):
    def test_only_explicit_open_licenses_qualify(self):
        self.assertEqual(allowed_license(page()["imageinfo"][0]), "Public domain")
        self.assertIsNone(allowed_license(page(licence="CC BY-NC 4.0")["imageinfo"][0]))
        self.assertIsNone(allowed_license(page(licence="All rights reserved")["imageinfo"][0]))

    def test_real_photo_rejected_if_wrong_place_or_art_or_ai(self):
        good = page()
        self.assertEqual(
            pick_media([good], "Vietnam military helicopter", kind="real", context="Vietnam War")["kind"], "image")
        wrong = page(title="File:Kyoto temple Japan.jpg", tags="Kyoto Japan ancient temple")
        self.assertIsNone(pick_media([wrong], "Vietnam military helicopter", kind="real", context="Vietnam War"))
        drawing = page(title="File:Vietnam war helicopter illustration.jpg")
        self.assertIsNone(pick_media([drawing], "Vietnam helicopter", kind="real"))
        self.assertEqual(pick_media([drawing], "Vietnam helicopter", kind="illustration")["kind"], "illustration")
        generated = page(title="File:Vietnam helicopter AI generated.jpg")
        self.assertIsNone(pick_media([generated], "Vietnam helicopter", kind="real"))

    def test_only_wikimedia_upload_hosts_allowed(self):
        validate_media_url("https://upload.wikimedia.org/wikipedia/commons/a/b/file.jpg")
        for url in ("https://evil.example/x.jpg", "http://upload.wikimedia.org/wikipedia/commons/x.jpg",
                    "https://upload.wikimedia.org.evil.test/wikipedia/commons/x.png",
                    "https://upload.wikimedia.org/other/x.jpg"):
            with self.assertRaises(PipelineError):
                validate_media_url(url)


class MediaPriorityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.scenes = [{"archive_queries": ["Vietnam war helicopter"],
                        "search_terms": ["military helicopter", "soldiers war"]}]

    @patch("fernimoon.media_sources.collect_footage")
    @patch("fernimoon.media_sources.find_and_download")
    def test_real_wikimedia_photo_precedes_stock(self, commons, stock):
        commons.return_value = {"kind": "image", "source": "Wikimedia Commons"}
        result = collect_priority_media(self.scenes, config(), self.work, self.work / "cache", "Vietnam War")
        self.assertEqual(result[0]["priority_tier"], 1)
        stock.assert_not_called()

    @patch("fernimoon.media_sources.collect_footage")
    @patch("fernimoon.media_sources.find_and_download")
    def test_stock_precedes_illustration(self, commons, stock):
        commons.return_value = None
        stock.return_value = [{"kind": "video", "source": "Pixabay"}]
        result = collect_priority_media(self.scenes, config(), self.work, self.work / "cache", "Vietnam War")
        self.assertEqual(result[0]["priority_tier"], 2)
        self.assertEqual(commons.call_count, 1)

    @patch("fernimoon.media_sources.collect_footage", side_effect=PipelineError("Pixabay: no context-relevant historical stock clip for scene 1."))
    @patch("fernimoon.media_sources.find_and_download")
    def test_illustration_is_only_last_fallback(self, commons, stock):
        commons.side_effect = [None, {"kind": "illustration", "source": "Wikimedia Commons"}]
        result = collect_priority_media(self.scenes, config(), self.work, self.work / "cache", "Vietnam War")
        self.assertEqual(result[0]["priority_tier"], 3)
        self.assertEqual([x.kwargs.get("kind") for x in commons.call_args_list], [None, None])
        self.assertEqual(commons.call_args_list[1].args[1], "illustration")

    @patch("fernimoon.media_sources.collect_footage", side_effect=PipelineError("Pixabay: HTTP 500"))
    @patch("fernimoon.media_sources.find_and_download", return_value=None)
    def test_stock_server_errors_do_not_justify_illustration(self, commons, stock):
        with self.assertRaisesRegex(PipelineError, "HTTP 500"):
            collect_priority_media(self.scenes, config(), self.work, self.work / "cache", "Vietnam War")
        self.assertEqual(commons.call_count, 1)


class SoundMomentTests(unittest.TestCase):
    def test_sound_schema_accepts_one_middle_scene(self):
        obj = example_script()
        obj["scenes"][2]["sound_cue"] = {"query": "helicopter rotor", "seconds": 1.5}
        valid = validate_script(obj, 40)
        self.assertEqual(valid["scenes"][2]["sound_cue"]["seconds"], 1.5)
        obj["scenes"][3]["sound_cue"] = {"query": "explosion", "seconds": 1.5}
        with self.assertRaisesRegex(PipelineError, "at most one"):
            validate_script(obj, 40)

    def test_pause_shifts_later_words_and_scene_cuts(self):
        scenes = [{"narration": "One two"}, {"narration": "Three four"},
                  {"narration": "Five six"}]
        words = [Word(x, 0.2 + i * 0.5, 0.35 + i * 0.5)
                 for i, x in enumerate("One two Three four Five six".split())]
        sound = {"after_scene": 1, "seconds": 1.5, "file": "sample.ogg"}
        updated, speed, cue = retime_with_sound(scenes, words, 3.5, 5, sound)
        self.assertAlmostEqual(speed, 1)
        self.assertAlmostEqual(updated[3].end, words[3].end)
        self.assertAlmostEqual(updated[4].start, words[4].start + 1.5)
        self.assertTrue(cue["start"] < updated[4].start)
        cuts = scene_boundaries(scenes, updated, 5)
        self.assertAlmostEqual(cuts[2], updated[4].start)

    def test_no_sound_means_no_forced_silence(self):
        words = [Word("hello", 0.1, 0.3), Word("there", 1.1, 1.3)]
        new, speed, cue = retime_with_sound([{"narration": "hello there"}],
                                            words, 2, 2, None)
        self.assertEqual(new, words)
        self.assertIsNone(cue)


if __name__ == "__main__":
    unittest.main()
