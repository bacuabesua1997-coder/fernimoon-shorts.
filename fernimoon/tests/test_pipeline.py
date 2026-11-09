import base64
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from fernimoon.captions import escape_ass, groups, make_ass, make_srt
from fernimoon.config import Config, PipelineError, validate_topic
from fernimoon.footage import collect_footage, search, select_footage
from fernimoon.http import VideoRedirectHandler, download_video, request_json, validate_video_url
from fernimoon.media import verify_output
from fernimoon.script import generate_script, validate_script
from fernimoon.speech import Word, alignment_words, retime, scene_boundaries, synthesize


def example_script():
    texts = [
        "Beneath the ocean surface, extraordinary animals hide in plain sight.",
        "Sea turtles travel across vast stretches of water, returning to familiar beaches to lay eggs.",
        "Coral reefs provide shelter for colorful fish and many other creatures that depend on them.",
        "Farther from shore, dolphins communicate through sounds while moving together in groups through the waves.",
        "Whales also use sound underwater, where calls can travel much farther than they do above.",
        "Protecting these habitats helps keep this remarkable underwater world alive for the generations still ahead.",
    ]
    return {"title": "An Ocean Full of Life", "description": "Explore the ocean. #Shorts #FERNIMOONSTUDIO",
            "scenes": [{"narration": text, "search_terms": ["ocean wildlife", "sea turtle"]} for text in texts]}


def example_hit(id=1, **overrides):
    return {"id": id, "type": "film", "tags": "ocean, waves", "duration": 10, "user": "Filmmaker",
            "pageURL": f"https://pixabay.com/videos/id-{id}/",
            "videos": {"medium": {"url": f"https://cdn.pixabay.com/video/{id}.mp4",
                                   "width": 1280, "height": 720, "size": 1024}}, **overrides}


def alignment(text):
    return {"characters": list(text), "character_start_times_seconds": [i * 0.05 for i in range(len(text))],
            "character_end_times_seconds": [(i + 1) * 0.05 for i in range(len(text))]}


def config():
    return Config("secret-gemini", "secret-pixabay", "secret-eleven", "voice123")


class ConfigurationTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_missing_secrets_are_named_without_values(self):
        with self.assertRaisesRegex(PipelineError, "GEMINI_API_KEY.*PIXABAY_API_KEY"):
            Config.from_env()

    def test_repr_excludes_keys(self):
        self.assertNotIn("secret-", repr(config()))

    @patch.dict(os.environ, {"GEMINI_API_KEY": "key", "PIXABAY_API_KEY": "key", "ELEVENLABS_API_KEY": "key",
                             "ELEVENLABS_VOICE_ID": "voice123", "GEMINI_MODEL": "", "ELEVENLABS_MODEL": ""}, clear=True)
    def test_defaults_and_duration_bounds(self):
        self.assertEqual(Config.from_env().gemini_model, "gemini-2.5-flash")
        with self.assertRaises(PipelineError):
            Config.from_env(34)
        os.environ["ELEVENLABS_VOICE_ID"] = "../../bad"
        with self.assertRaises(PipelineError):
            Config.from_env()

    @patch.dict(os.environ, {"GEMINI_API_KEY": "key", "PIXABAY_API_KEY": "key",
                             "ELEVENLABS_API_KEY": "key", "ELEVENLABS_VOICE_ID": "voice123",
                             "SHORTS_STYLE": "history"}, clear=True)
    def test_history_style_config_and_invalid_style(self):
        self.assertEqual(Config.from_env().story_style, "history")
        os.environ["SHORTS_STYLE"] = "unsafe"
        with self.assertRaisesRegex(PipelineError, "SHORTS_STYLE"):
            Config.from_env()

    def test_topic_constraints(self):
        self.assertEqual(validate_topic("  Ocean\n life "), "Ocean life")
        for value in ("", "a" * 301):
            with self.assertRaises(PipelineError):
                validate_topic(value)


class ScriptTests(unittest.TestCase):
    def test_accepts_english_script_with_bounded_length(self):
        self.assertEqual(len(validate_script(example_script(), 40)["scenes"]), 6)

    def test_opening_hook_and_payoff_have_bounded_word_counts(self):
        data = example_script()
        data["scenes"][0]["narration"] = "The story begins with an unusually long introduction that reveals very little about the key point of the topic."
        with self.assertRaisesRegex(PipelineError, "opening hook"):
            validate_script(data, 40)
        data = example_script()
        data["scenes"][-1]["narration"] = "One two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty."
        with self.assertRaisesRegex(PipelineError, "closing payoff"):
            validate_script(data, 40)

    def test_rejects_empty_long_wrong_language_and_missing_queries(self):
        bad_scripts = []
        data = example_script(); data["scenes"] = []; bad_scripts.append(data)
        data = example_script(); data["scenes"][0]["narration"] = "word " * 31; bad_scripts.append(data)
        data = example_script(); data["scenes"][0]["narration"] = "Đây là câu chuyện về những con sóng biển xanh"; bad_scripts.append(data)
        data = example_script(); data["scenes"][0]["search_terms"] = ["ocean"]; bad_scripts.append(data)
        for data in bad_scripts:
            with self.assertRaises(PipelineError):
                validate_script(data, 40)

    @patch("fernimoon.script.request_json")
    def test_gemini_retries_invalid_script_and_uses_header_key(self, request):
        good = {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(example_script())}]}}]}
        request.side_effect = [{"candidates": []}, good]
        self.assertEqual(generate_script('Ocean $(echo unsafe)', config())["title"], example_script()["title"])
        self.assertEqual(request.call_count, 2)
        args, kwargs = request.call_args
        self.assertNotIn("secret-gemini", args[0])
        self.assertEqual(kwargs["headers"]["x-goog-api-key"], "secret-gemini")
        self.assertEqual(kwargs["body"]["generationConfig"]["responseMimeType"], "application/json")
        prompt = kwargs["body"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("FIVE TO TWELVE", prompt)
        self.assertIn("satisfying", prompt.lower())

    @patch("fernimoon.script.request_json")
    def test_story_style_changes_prompt_without_changing_api(self, request):
        request.return_value = {"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(example_script())}]}}]}
        from dataclasses import replace
        generate_script("A documented historical event", replace(config(), story_style="history"))
        prompt = request.call_args.kwargs["body"]["systemInstruction"]["parts"][0]["text"]
        self.assertIn("historical event", prompt)
        self.assertIn("modern stock footage", prompt)

    @patch("fernimoon.script.request_json", return_value={"candidates": [{"finishReason": "MAX_TOKENS"}]})
    def test_blocked_or_truncated_script_fails_after_two_attempts(self, request):
        with self.assertRaises(PipelineError):
            generate_script("Ocean", config())
        self.assertEqual(request.call_count, 2)


class FootageTests(unittest.TestCase):
    def test_rejects_images_animations_ai_tags_duplicates_and_low_resolution(self):
        for hit in (example_hit(type="photo"), example_hit(type="animation"), example_hit(tags="ocean, AI generated"),
                    example_hit(isAiGenerated=True), example_hit(duration=0), example_hit(videos={})):
            self.assertIsNone(select_footage([hit], set()))
        self.assertIsNone(select_footage([example_hit()], {1}))
        self.assertEqual(select_footage([example_hit()], set())["id"], 1)

    def test_prefers_portrait(self):
        portrait = example_hit(2)
        portrait["videos"]["medium"].update(width=1080, height=1920)
        self.assertEqual(select_footage([example_hit(), portrait], set())["id"], 2)

    def test_only_pixabay_https_mp4_is_allowed(self):
        validate_video_url("https://cdn.pixabay.com/video/clip.mp4")
        for url in ("https://evil.example/clip.mp4", "http://cdn.pixabay.com/clip.mp4", "file:///clip.mp4",
                    "https://cdn.pixabay.com/clip.jpg", "https://cdn.pixabay.com.evil.example/clip.mp4",
                    "https://user:pass@cdn.pixabay.com/clip.mp4", "https://cdn.pixabay.com:123/clip.mp4"):
            with self.assertRaises(PipelineError):
                validate_video_url(url)

    def test_redirects_cannot_leave_pixabay(self):
        with self.assertRaises(PipelineError):
            VideoRedirectHandler().redirect_request(None, None, 302, "redirect", {}, "https://evil.example/file.mp4")

    @patch("fernimoon.http.urllib.request.build_opener")
    def test_failed_download_removes_partial_file(self, opener):
        stream = opener.return_value.open.return_value.__enter__.return_value
        stream.geturl.return_value = "https://cdn.pixabay.com/video/test.mp4"
        stream.headers = {"Content-Type": "video/mp4"}
        stream.read.side_effect = [b"partial", TimeoutError()]
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "footage.mp4"
            with self.assertRaises(PipelineError):
                download_video("https://cdn.pixabay.com/video/test.mp4", destination, retries=0)
            self.assertFalse(destination.exists())
            self.assertFalse(destination.with_suffix(".part").exists())

    @patch("fernimoon.footage.request_json", return_value={"hits": [example_hit()]})
    def test_cache_avoids_duplicate_requests_and_never_stores_key(self, request):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            self.assertEqual(search("ocean", "TOP_SECRET", cache), search("ocean", "TOP_SECRET", cache))
            self.assertEqual(request.call_count, 1)
            path = next(cache.glob("*.json"))
            self.assertNotIn("TOP_SECRET", path.read_text())
            os.utime(path, (0, 0))
            search("ocean", "TOP_SECRET", cache)
            self.assertEqual(request.call_count, 2)
            self.assertIn("video_type=film", request.call_args.args[0])

    @patch("fernimoon.footage.download_video")
    @patch("fernimoon.footage.search")
    def test_fallback_queries_and_source_manifest(self, search_mock, download):
        search_mock.side_effect = [[], [example_hit()]]
        with tempfile.TemporaryDirectory() as tmp:
            result = collect_footage([{"search_terms": ["rare subject", "ocean"]}], "key", Path(tmp), Path(tmp))
        self.assertEqual(result[0]["search_query"], "ocean")
        self.assertIn("license_url", result[0])
        download.assert_called_once()

    @patch("fernimoon.footage.search", return_value=[])
    def test_missing_footage_stops_instead_of_using_images(self, search_mock):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaisesRegex(PipelineError, "no suitable"):
            collect_footage([{"search_terms": ["unavailable"]}], "key", Path(tmp), Path(tmp))


class SpeechTests(unittest.TestCase):
    def test_alignment_converts_characters_to_real_word_onsets(self):
        words = alignment_words(alignment("Hello world!"), "Hello world!")
        self.assertEqual([w.text for w in words], ["Hello", "world!"])
        self.assertAlmostEqual(words[1].start, 0.3)
        self.assertAlmostEqual(words[1].end, 0.6)

    def test_rejects_mismatch_nan_missing_and_reversed_timestamps(self):
        examples = [{}, alignment("Wrong text")]
        data = alignment("Hello world"); data["character_start_times_seconds"][3] = float("nan"); examples.append(data)
        data = alignment("Hello world"); data["character_end_times_seconds"][0] = -1; examples.append(data)
        data = alignment("Hello world"); data["character_start_times_seconds"].pop(); examples.append(data)
        for data in examples:
            with self.assertRaises(PipelineError):
                alignment_words(data, "Hello world")

    def test_tempo_updates_captions_and_scene_cuts_together(self):
        words = [Word("Hello", 0, 5), Word("world", 20, 35)]
        updated, speed = retime(words, 44, 40)
        self.assertAlmostEqual(speed, 1.1)
        self.assertAlmostEqual(updated[1].start, 20 / 1.1)
        self.assertEqual(scene_boundaries([{"narration": "Hello"}, {"narration": "world"}], updated, 40),
                         [0.0, 20 / 1.1, 40])

    def test_short_narration_is_padded_not_unaturally_stretched(self):
        words, speed = retime([Word("Hello", 0, 10), Word("world", 18, 20)], 20, 40)
        self.assertAlmostEqual(speed, 0.8)
        self.assertAlmostEqual(words[-1].end, 25)
        self.assertLess(words[-1].end, 40)

    def test_long_narration_and_out_of_audio_alignment_fail(self):
        with self.assertRaisesRegex(PipelineError, "too long"):
            retime([Word("Hello", 0, 50)], 50, 40)
        with self.assertRaises(PipelineError):
            retime([Word("Hello", 0, 45)], 40, 40)

    @patch("fernimoon.speech.request_json")
    def test_speech_uses_timestamps_endpoint_without_paid_retry(self, request):
        request.return_value = {"alignment": alignment("Hello world"), "audio_base64": base64.b64encode(b"x" * 200).decode()}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "voice.mp3"
            self.assertEqual(len(synthesize("Hello world", config(), path)), 2)
            self.assertEqual(path.stat().st_size, 200)
        self.assertIn("/with-timestamps?", request.call_args.args[0])
        self.assertEqual(request.call_args.kwargs["retries"], 0)
        self.assertEqual(request.call_args.kwargs["body"]["language_code"], "en")


class CaptionTests(unittest.TestCase):
    def test_ass_highlight_and_srt_follow_spoken_words(self):
        words = [Word("Hello", 1.25, 1.8), Word("ocean!", 2, 2.6)]
        ass = make_ass(words, 40)
        self.assertNotIn("FERNIMOON STUDIO", ass)
        self.assertIn("0:00:01.25", ass)
        self.assertIn(r"\c&H00E8FF&", ass)
        self.assertIn("Style: Hook", ass)
        self.assertIn("0:00:01.25,0:00:01.95,Hook", ass)
        self.assertIn("00:00:01,250 --> 00:00:02,600", make_srt(words))
        self.assertNotIn(r"\pos", escape_ass(r"{\pos(0,0)}oops"))

    def test_caption_groups_stay_short(self):
        words = [Word("turtle", i, i + 0.9) for i in range(10)]
        self.assertTrue(all(len(g) <= 4 for g in groups(words)))
        self.assertEqual(sum(len(g) for g in groups(words)), 10)


class HttpTests(unittest.TestCase):
    @patch("fernimoon.http.time.sleep")
    @patch("fernimoon.http.urllib.request.urlopen")
    def test_retries_rate_limits_but_redacts_keys(self, urlopen, sleep):
        url = "https://pixabay.com/api/videos/?key=TOP_SECRET"
        urlopen.side_effect = urllib.error.HTTPError(url, 429, "TOP_SECRET", {}, None)
        with self.assertRaises(PipelineError) as error:
            request_json(url, service="Pixabay")
        self.assertNotIn("TOP_SECRET", str(error.exception))
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("fernimoon.http.urllib.request.urlopen")
    def test_auth_errors_and_paid_tts_requests_are_not_retried(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError("https://api.example/", 401, "SECRET", {}, None)
        with self.assertRaisesRegex(PipelineError, "HTTP 401"):
            request_json("https://api.example/", service="Test")
        self.assertEqual(urlopen.call_count, 1)
        urlopen.reset_mock()
        urlopen.side_effect = urllib.error.URLError("SECRET")
        with self.assertRaises(PipelineError) as error:
            request_json("https://api.example/", service="ElevenLabs", body={}, retries=0)
        self.assertEqual(urlopen.call_count, 1)
        self.assertNotIn("SECRET", str(error.exception))

    @patch("fernimoon.http.urllib.request.urlopen")
    def test_malformed_json_fails_safely(self, urlopen):
        urlopen.return_value.__enter__.return_value = io.BytesIO(b"not json SECRET")
        with self.assertRaisesRegex(PipelineError, "malformed JSON"):
            request_json("https://api.example/", service="Test")


class OutputTests(unittest.TestCase):
    @patch("fernimoon.media.probe")
    def test_final_output_must_have_full_audio_and_video(self, probe):
        good = {"format": {"duration": "40"}, "streams": [
            {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p", "width": 1080, "height": 1920, "duration": "40"},
            {"codec_type": "audio", "codec_name": "aac", "duration": "40"}]}
        probe.return_value = good
        self.assertEqual(verify_output(Path("video.mp4"), 40)["duration"], 40)
        good["streams"][1]["duration"] = "12"
        with self.assertRaises(PipelineError):
            verify_output(Path("video.mp4"), 40)


if __name__ == "__main__":
    unittest.main()
