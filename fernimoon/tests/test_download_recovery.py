"""Regression tests for Actions run 42184840403. No network or API keys required."""
import http.client
import io
import json
import tempfile
import traceback
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from fernimoon.config import PipelineError
from fernimoon.footage import MAX_CANDIDATES_PER_QUERY, collect_footage, search
from fernimoon.http import MAX_RETRY_DELAY, VideoDownloadError, download_video, retry_delay
from test_pipeline import example_hit


URL = "https://cdn.pixabay.com/video/test.mp4?key=SECRET_KEY&signature=SECRET_SIGNATURE"
NEW_URL = "https://cdn.pixabay.com/video/new.mp4?signature=NEW_SECRET_SIGNATURE"
PAYLOAD = b"\x00\x00\x00\x18ftypmp42video-fixture"


class Response(io.BytesIO):
    def __init__(self, data=PAYLOAD, *, url=URL, headers=None):
        super().__init__(data)
        self.url = url
        self.headers = headers if headers is not None else {"Content-Type": "video/mp4", "Content-Length": str(len(data))}

    def geturl(self):
        return self.url


def http_error(code, headers=None):
    return urllib.error.HTTPError(URL, code, "SECRET_KEY SECRET_SIGNATURE", headers or {}, io.BytesIO(b"SECRET_BODY"))


def cdn_error(code=403):
    return VideoDownloadError(f"HTTP {code}", "cdn.pixabay.com", 1, status=code)


class DownloadRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.destination = Path(self.tmp.name) / "clip.mp4"
        patcher = patch("fernimoon.http.urllib.request.build_opener")
        self.opener = patcher.start().return_value
        self.addCleanup(patcher.stop)
        sleeper = patch("fernimoon.http.time.sleep")
        self.sleep = sleeper.start()
        self.addCleanup(sleeper.stop)
        self.log = io.StringIO()
        output = redirect_stdout(self.log)
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def assert_no_secrets(self, message=""):
        combined = self.log.getvalue() + message
        for token in ("SECRET_KEY", "SECRET_SIGNATURE", "SECRET_BODY", "https://", "?key=", "?signature="):
            self.assertNotIn(token, combined)

    def test_transient_http_statuses_retry_then_succeed_with_explicit_headers(self):
        for code in (408, 429, 500, 502, 503, 504):
            with self.subTest(code=code):
                self.opener.open.reset_mock()
                self.sleep.reset_mock()
                self.opener.open.side_effect = [http_error(code), Response()]
                download_video(URL, self.destination)
                self.assertEqual(self.destination.read_bytes(), PAYLOAD)
                self.assertEqual(self.opener.open.call_count, 2)
                self.sleep.assert_called_once_with(2)
                request = self.opener.open.call_args.args[0]
                self.assertIsInstance(request, urllib.request.Request)
                self.assertEqual(request.get_header("User-agent"), "FERNIMOON-STUDIO/1.0")
                self.assertIn("video/mp4", request.get_header("Accept"))
                self.assertIn(f"HTTP {code}", self.log.getvalue())
        self.assert_no_secrets()

    def test_retry_after_is_respected_and_bounded(self):
        self.opener.open.side_effect = [http_error(429, {"Retry-After": "7"}),
                                       http_error(503, {"Retry-After": "99999"}), Response()]
        download_video(URL, self.destination)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [7, MAX_RETRY_DELAY])
        self.assert_no_secrets()

    def test_permanent_errors_are_not_retried_and_report_only_status_and_host(self):
        for code in (400, 401, 403, 404, 410, 451):
            with self.subTest(code=code):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [http_error(code)]
                with self.assertRaises(VideoDownloadError) as caught:
                    download_video(URL, self.destination)
                self.assertEqual(caught.exception.status, code)
                self.assertEqual(caught.exception.refresh_url, code in (401, 403, 404, 410))
                self.assertIn(f"HTTP {code}", str(caught.exception))
                self.assertEqual(self.opener.open.call_count, 1)
                self.assertFalse(self.destination.exists())
                self.assert_no_secrets("".join(traceback.format_exception(caught.exception)))

    def test_transient_failure_exhausts_only_three_attempts_and_removes_partial(self):
        self.opener.open.side_effect = [http_error(503) for _ in range(3)]
        with self.assertRaises(VideoDownloadError) as caught:
            download_video(URL, self.destination)
        self.assertEqual(self.opener.open.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertIn("attempts 3", str(caught.exception))
        self.assertFalse(self.destination.with_suffix(".part").exists())
        self.assert_no_secrets(str(caught.exception))

    def test_connection_and_incomplete_read_failures_retry_without_raw_exception(self):
        for error in (urllib.error.URLError("SECRET_KEY"), TimeoutError("SECRET_KEY"),
                      ConnectionResetError("SECRET_SIGNATURE"), http.client.IncompleteRead(b"SECRET_BODY")):
            with self.subTest(error=type(error).__name__):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [error, Response()]
                download_video(URL, self.destination)
                self.assertEqual(self.destination.read_bytes(), PAYLOAD)
                self.assertEqual(self.opener.open.call_count, 2)
        self.assert_no_secrets()

    def test_interrupted_stream_restarts_from_zero_without_append(self):
        interrupted = Mock(wraps=Response())
        interrupted.headers = {"Content-Type": "video/mp4"}
        interrupted.geturl.return_value = URL
        interrupted.__enter__ = Mock(return_value=interrupted)
        interrupted.__exit__ = Mock(return_value=False)
        interrupted.read.side_effect = [b"old partial", TimeoutError("SECRET_KEY")]
        self.opener.open.side_effect = [interrupted, Response()]
        download_video(URL, self.destination)
        self.assertEqual(self.destination.read_bytes(), PAYLOAD)
        self.assertFalse(self.destination.with_suffix(".part").exists())
        self.assert_no_secrets()

    def test_empty_and_short_content_length_are_retried(self):
        for response in (Response(b""), Response(b"partial", headers={"Content-Length": "100"})):
            self.opener.open.side_effect = [response, Response()]
            download_video(URL, self.destination)
            self.assertEqual(self.destination.read_bytes(), PAYLOAD)

    def test_html_or_oversize_responses_do_not_become_video_files(self):
        for headers in ({"Content-Type": "text/html; charset=utf-8"}, {"Content-Length": str(151 * 1024 * 1024)}):
            with self.subTest(headers=headers):
                self.opener.open.reset_mock()
                self.opener.open.side_effect = [Response(b"SECRET_BODY", headers=headers)]
                with self.assertRaises(VideoDownloadError) as caught:
                    download_video(URL, self.destination)
                self.assertEqual(self.opener.open.call_count, 1)
                self.assertFalse(self.destination.exists())
                self.assertFalse(self.destination.with_suffix(".part").exists())
                self.assert_no_secrets(str(caught.exception))

    @patch("fernimoon.http.MAX_VIDEO_BYTES", 3)
    def test_streamed_size_limit_still_applies_without_content_length(self):
        self.opener.open.side_effect = [Response(headers={})]
        with self.assertRaises(VideoDownloadError):
            download_video(URL, self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(self.destination.with_suffix(".part").exists())

    def test_failed_transfer_does_not_replace_an_existing_file(self):
        self.destination.write_bytes(b"previous good file")
        self.opener.open.side_effect = [http_error(404)]
        with self.assertRaises(VideoDownloadError):
            download_video(URL, self.destination)
        self.assertEqual(self.destination.read_bytes(), b"previous good file")

    def test_source_policy_failure_cannot_be_retried_or_accepted(self):
        for url in ("http://cdn.pixabay.com/test.mp4", "https://evil.example/test.mp4?key=SECRET_KEY",
                    "https://cdn.pixabay.com:bad/test.mp4", "https://[bad/test.mp4", None):
            with self.subTest(url=url):
                with self.assertRaises(PipelineError) as caught:
                    download_video(url, self.destination)
                self.assert_no_secrets(str(caught.exception))
        self.opener.open.assert_not_called()
        self.opener.open.side_effect = [Response(url="https://evil.example/test.mp4?key=SECRET_KEY")]
        with self.assertRaises(PipelineError):
            download_video(URL, self.destination)
        self.sleep.assert_not_called()
        self.assertFalse(self.destination.exists())

    def test_local_file_error_is_fatal_not_a_clip_failure(self):
        self.opener.open.side_effect = [Response()]
        with patch.object(Path, "open", side_effect=PermissionError("SECRET_KEY")):
            with self.assertRaises(PipelineError) as caught:
                download_video(URL, self.destination)
        self.assertNotIsInstance(caught.exception, VideoDownloadError)
        self.sleep.assert_not_called()
        self.assert_no_secrets(str(caught.exception))

    @patch("fernimoon.http.time.time", return_value=0)
    def test_retry_after_http_date_and_invalid_values(self, clock):
        self.assertEqual(retry_delay("Thu, 01 Jan 1970 00:00:12 GMT", 0), 12)
        self.assertEqual(retry_delay("Thu, 01 Jan 1970 01:00:00 GMT", 0), MAX_RETRY_DELAY)
        self.assertEqual(retry_delay("SECRET_KEY invalid header", 1), 4)
        self.assertEqual(retry_delay(None, 0), 2)


class CandidateRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.scenes = [{"search_terms": ["ocean", "waves"]}]
        self.log = io.StringIO()
        output = redirect_stdout(self.log)
        output.__enter__()
        self.addCleanup(output.__exit__, None, None, None)

    def collect(self):
        return collect_footage(self.scenes, "SECRET_KEY", self.work, self.work / "cache")

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_exhausted_transient_clip_switches_to_another_id_and_records_only_success(self, download, search_mock):
        search_mock.return_value = [example_hit(1), example_hit(2)]
        download.side_effect = [cdn_error(503), None]
        result = self.collect()
        self.assertEqual([r["id"] for r in result], [2])
        self.assertEqual(result[0]["search_query"], "ocean")
        self.assertEqual(download.call_count, 2)
        self.assertEqual(search_mock.call_count, 1)
        self.assertNotIn("SECRET_KEY", self.log.getvalue())

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_expired_url_is_refreshed_once_and_success_uses_new_metadata(self, download, search_mock):
        fresh = example_hit()
        fresh["videos"]["medium"]["url"] = NEW_URL
        search_mock.side_effect = [[example_hit()], [fresh]]
        download.side_effect = [cdn_error(403), None]
        result = self.collect()
        self.assertEqual(result[0]["url"], NEW_URL)
        self.assertTrue(search_mock.call_args.kwargs["force_refresh"])
        self.assertEqual(download.call_args.args[0], NEW_URL)
        self.assertNotIn("NEW_SECRET_SIGNATURE", self.log.getvalue())

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_unchanged_expired_url_is_not_downloaded_again(self, download, search_mock):
        search_mock.return_value = [example_hit(1), example_hit(2)]
        download.side_effect = [cdn_error(404), None]
        self.assertEqual(self.collect()[0]["id"], 2)
        self.assertEqual([c.args[0] for c in download.call_args_list],
                         ["https://cdn.pixabay.com/video/1.mp4", "https://cdn.pixabay.com/video/2.mp4"])
        self.assertEqual(search_mock.call_count, 2)

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_changed_url_that_still_fails_falls_back_without_refresh_loop(self, download, search_mock):
        fresh = example_hit()
        fresh["videos"]["medium"]["url"] = NEW_URL
        search_mock.side_effect = [[example_hit()], [fresh, example_hit(2)]]
        download.side_effect = [cdn_error(403), cdn_error(403), None]
        self.assertEqual(self.collect()[0]["id"], 2)
        self.assertEqual(search_mock.call_count, 2)
        self.assertEqual(download.call_count, 3)

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_multiple_expired_candidates_refresh_a_query_only_once(self, download, search_mock):
        search_mock.return_value = [example_hit(1), example_hit(2), example_hit(3)]
        download.side_effect = [cdn_error(403), cdn_error(410), None]
        self.assertEqual(self.collect()[0]["id"], 3)
        self.assertEqual(search_mock.call_count, 2)
        self.assertEqual(sum(bool(c.kwargs.get("force_refresh")) for c in search_mock.call_args_list), 1)

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_refresh_failure_still_tries_other_cached_candidates(self, download, search_mock):
        search_mock.side_effect = [[example_hit(1), example_hit(2)], PipelineError("Pixabay: HTTP 503.")]
        download.side_effect = [cdn_error(410), None]
        self.assertEqual(self.collect()[0]["id"], 2)

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_refreshed_metadata_must_still_pass_film_ai_and_url_checks(self, download, search_mock):
        for unsafe in (example_hit(type="animation"), example_hit(tags="AI generated"),
                       example_hit(videos={"medium": {"url": "https://evil.example/clip.mp4", "width": 1080, "height": 1920, "size": 100}})):
            with self.subTest(unsafe=unsafe):
                download.reset_mock()
                search_mock.side_effect = [[example_hit()], [unsafe, example_hit(2)]]
                download.side_effect = [cdn_error(403), None]
                self.assertEqual(self.collect()[0]["id"], 2)
                self.assertEqual(download.call_args.args[0], "https://cdn.pixabay.com/video/2.mp4")

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_fallback_to_next_query_does_not_retry_failed_ids(self, download, search_mock):
        search_mock.side_effect = [[example_hit(1)], [example_hit(1), example_hit(2)]]
        download.side_effect = [cdn_error(503), None]
        result = self.collect()
        self.assertEqual(result[0]["search_query"], "waves")
        self.assertEqual(result[0]["id"], 2)
        self.assertEqual(download.call_count, 2)

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_successful_ids_are_not_reused_in_later_scenes(self, download, search_mock):
        self.scenes *= 2
        search_mock.return_value = [example_hit(1), example_hit(2), example_hit(3)]
        download.side_effect = [cdn_error(503), None, None]
        self.assertEqual([r["id"] for r in self.collect()], [2, 3])

    @patch("fernimoon.footage.search")
    @patch("fernimoon.footage.download_video")
    def test_candidate_attempts_are_bounded_and_failure_is_actionable(self, download, search_mock):
        self.scenes = [{"search_terms": ["ocean"]}]
        search_mock.return_value = [example_hit(i) for i in range(20)]
        download.side_effect = cdn_error(503)
        with self.assertRaisesRegex(PipelineError, "no downloadable.*scene 1.*HTTP 503") as caught:
            self.collect()
        self.assertEqual(download.call_count, MAX_CANDIDATES_PER_QUERY)
        self.assertNotIn("SECRET_KEY", str(caught.exception) + self.log.getvalue())

    @patch("fernimoon.footage.search", return_value=[example_hit(1), example_hit(2)])
    @patch("fernimoon.footage.download_video", side_effect=PipelineError("Pixabay: refused a video URL outside the approved MP4 CDN."))
    def test_source_policy_errors_are_not_swallowed_by_candidate_fallback(self, download, search_mock):
        with self.assertRaisesRegex(PipelineError, "refused"):
            self.collect()
        self.assertEqual(download.call_count, 1)


class CacheRefreshTests(unittest.TestCase):
    @patch("fernimoon.http.time.sleep")
    @patch("fernimoon.http.urllib.request.build_opener")
    @patch("fernimoon.footage.request_json")
    def test_cached_expiration_refresh_and_http_retry_work_together(self, request, build_opener, sleep):
        old = example_hit()
        old["videos"]["medium"]["url"] = URL
        fresh = example_hit()
        fresh["videos"]["medium"]["url"] = NEW_URL
        request.side_effect = [{"hits": [old]}, {"hits": [fresh]}]
        opener = build_opener.return_value
        opener.open.side_effect = [http_error(403), http_error(503), Response(url=NEW_URL)]
        log = io.StringIO()
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(log):
            work = Path(directory)
            cache = work / "cache"
            search("ocean", "SECRET_KEY", cache)  # Fill a still-fresh metadata cache with an expired URL.
            sources = collect_footage([{"search_terms": ["ocean"]}], "SECRET_KEY", work, cache)
            self.assertEqual((work / sources[0]["file"]).read_bytes(), PAYLOAD)
            self.assertEqual(sources[0]["url"], NEW_URL)
            self.assertEqual(search("ocean", "SECRET_KEY", cache), [fresh])
            self.assertEqual(request.call_count, 2)
            self.assertEqual(opener.open.call_count, 3)
            sleep.assert_called_once_with(2)
        self.assertIn("HTTP 403", log.getvalue())
        self.assertIn("HTTP 503", log.getvalue())
        self.assertNotIn("SECRET", log.getvalue())
        self.assertNotIn("https://", log.getvalue())

    @patch("fernimoon.footage.request_json")
    def test_force_refresh_replaces_cached_urls_before_ttl_expires(self, request):
        fresh = example_hit()
        fresh["videos"]["medium"]["url"] = NEW_URL
        request.side_effect = [{"hits": [example_hit()]}, {"hits": [fresh]}]
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            search("ocean", "SECRET_KEY", cache)
            self.assertEqual(search("ocean", "SECRET_KEY", cache, force_refresh=True), [fresh])
            self.assertEqual(search("ocean", "SECRET_KEY", cache), [fresh])
            self.assertEqual(request.call_count, 2)
            self.assertNotIn("SECRET_KEY", next(cache.glob("*.json")).read_text())

    @patch("fernimoon.footage.request_json")
    def test_failed_refresh_does_not_preserve_known_stale_cache(self, request):
        request.side_effect = [{"hits": [example_hit()]}, PipelineError("Pixabay: HTTP 503.")]
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            search("ocean", "SECRET_KEY", cache)
            with self.assertRaises(PipelineError):
                search("ocean", "SECRET_KEY", cache, force_refresh=True)
            self.assertEqual(list(cache.glob("*.json")), [])

    @patch("fernimoon.footage.request_json", return_value={"hits": []})
    def test_corrupt_cache_hit_type_triggers_new_search(self, request):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            search("ocean", "SECRET_KEY", cache)
            next(cache.glob("*.json")).write_text(json.dumps({"hits": "invalid"}))
            self.assertEqual(search("ocean", "SECRET_KEY", cache), [])
            self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
