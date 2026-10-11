from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from pocket_clip_selector.api import create_app
from pocket_clip_selector.config import Settings, load_settings
from pocket_clip_selector.errors import AppError
from pocket_clip_selector.controller import ControllerOwnership
from pocket_clip_selector.library import sort_key
from pocket_clip_selector.mp4 import duration
from pocket_clip_selector.process_lock import ProcessLock
from helpers import make_project, mp4_bytes


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve() / "Media Projects"
        self.root.mkdir()
        self.project, self.file = make_project(self.root)
        self.controller = ControllerOwnership()
        self.app = create_app(Settings(self.root), controller=self.controller, lock_library=False)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.page = "first-page-identity-1234"
        self.token = self.client.post("/api/controller/claim", json={"page_id": self.page}).json()["token"]
        self.headers = {"X-Page-Id": self.page, "X-Controller-Token": self.token}
        self.query = {"project": self.project}
        self.path = self.root / self.project / ".clipselector" / "selections.json"

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temporary.cleanup()

    def capture(self, moment=50.125, identity="capture-identity-1234"):
        return self.client.post("/api/selections/capture", params=self.query, headers=self.headers,
                                json={"file": self.file, "time": moment, "id": identity})

    def test_discovery_only_immediate_projects_and_top_level_mp4(self):
        make_project(self.root, "z Project", "no conventions.MP4")
        make_project(self.root, "a project", "z.mp4")
        (self.root / "loose.mp4").write_bytes(b"loose")
        folder = self.root / self.project
        for name in ["Source", ".clipselector", "Nested"]:
            nested = folder / name
            nested.mkdir()
            (nested / "must-ignore.mp4").write_bytes(b"nested")
        (folder / "original.mkv").write_bytes(b"source")
        (folder / "B.mp4").write_bytes(mp4_bytes())
        (folder / "b-second.MP4").write_bytes(mp4_bytes())
        result = self.client.get("/api/projects", headers=self.headers).json()["projects"]
        self.assertEqual([row["name"] for row in result], sorted([self.project, "z Project", "a project"], key=lambda name: (name.casefold(), name)))
        media = self.client.get("/api/project", params=self.query, headers=self.headers).json()["media"]
        self.assertEqual([row["name"] for row in media], sorted([self.file, "B.mp4", "b-second.MP4"], key=lambda name: (name.casefold(), name)))
        self.assertEqual(next(row for row in result if row["name"] == self.project)["media_count"], 3)

    def test_empty_project_and_no_manifest_needed(self):
        (self.root / "Empty movie").mkdir()
        self.assertEqual(self.client.get("/api/project", params={"project": "Empty movie"}, headers=self.headers).json()["media"], [])
        self.assertFalse(self.path.parent.exists())
        self.assertEqual(self.client.get("/api/selections", params=self.query, headers=self.headers).json()["selections"], [])
        self.assertFalse(self.path.parent.exists())

    def test_full_stream_and_middle_byte_range_preserve_exact_names(self):
        query = {**self.query, "file": self.file}
        payload = (self.root / self.project / self.file).read_bytes()
        response = self.client.get("/media", params=query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, payload)
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertEqual(response.headers["content-disposition"], "inline")
        response = self.client.get("/media", params=query, headers={"Range": "bytes=700-899"})
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.content, payload[700:900])
        self.assertEqual(response.headers["content-range"], f"bytes 700-899/{len(payload)}")
        self.assertEqual(response.headers["content-length"], "200")

    def test_suffix_open_ended_and_oversized_end_ranges(self):
        payload = (self.root / self.project / self.file).read_bytes()
        for range_header, expected in [("bytes=-12", payload[-12:]), ("bytes=1000-", payload[1000:]),
                                       ("bytes=1000-999999", payload[1000:]), ("bytes=-999999", payload)]:
            with self.subTest(range_header=range_header):
                response = self.client.get("/media", params={**self.query, "file": self.file}, headers={"Range": range_header})
                self.assertEqual(response.status_code, 206)
                self.assertEqual(response.content, expected)

    def test_invalid_ranges_and_empty_files(self):
        for value in ["bytes=99999-", "bytes=100-1", "bytes=-0", "bytes=-", "bytes=oops", "bytes=1.5-2", "bytes=" + "9" * 5000 + "-"]:
            with self.subTest(value=value):
                response = self.client.get("/media", params={**self.query, "file": self.file}, headers={"Range": value})
                self.assertEqual(response.status_code, 416)
                self.assertTrue(response.headers["content-range"].startswith("bytes */"))
                self.assertEqual(response.content, b"")
        (self.root / self.project / "empty.mp4").touch()
        response = self.client.get("/media", params={**self.query, "file": "empty.mp4"}, headers={"Range": "bytes=0-1"})
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response.headers["content-range"], "bytes */0")

    def test_head_if_range_and_ignored_multi_range(self):
        query = {**self.query, "file": self.file}
        full = self.client.get("/media", params=query)
        head = self.client.head("/media", params=query, headers={"Range": "bytes=0-1"})
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")
        self.assertEqual(head.headers["content-length"], full.headers["content-length"])
        partial = self.client.get("/media", params=query, headers={"Range": "bytes=0-1", "If-Range": full.headers["etag"]})
        self.assertEqual(partial.status_code, 206)
        stale = self.client.get("/media", params=query, headers={"Range": "bytes=0-1", "If-Range": '"old"'})
        self.assertEqual(stale.status_code, 200)
        for value in ["bytes=0-1,5-6", "items=0-1"]:
            self.assertEqual(self.client.get("/media", params=query, headers={"Range": value}).status_code, 200)

    def test_capture_fractional_time_and_clamping(self):
        for index, moment in enumerate([2.125, 50.125, 119.75, 0, 120.5]):
            response = self.capture(moment, f"identity-{index:016}")
            self.assertEqual(response.status_code, 201, response.text)
            saved = next(row for row in response.json()["selections"] if row["id"] == f"identity-{index:016}")
            self.assertEqual(saved["start"], max(0, moment - 15))
            self.assertEqual(saved["end"], min(120.5, moment + 15))
        self.assertEqual(len(json.loads(self.path.read_text())["selections"]), 5)

    def test_manual_add_edit_delete_and_restart_persistence(self):
        response = self.client.post("/api/selections", params=self.query, headers=self.headers,
                                    json={"id": "manual-range-identity", "file": self.file, "start": 20.25, "end": 80.875})
        self.assertEqual(response.status_code, 201)
        revision = response.json()["revision"]
        edited = self.client.patch("/api/selections/manual-range-identity", params=self.query,
                                   headers={**self.headers, "If-Match": revision}, json={"start": 19.75, "end": 81.375})
        self.assertEqual(edited.status_code, 200)
        with TestClient(create_app(Settings(self.root), lock_library=False)) as restarted:
            token = restarted.post("/api/controller/claim", json={"page_id": "restarted-page-identity"}).json()["token"]
            headers = {"X-Page-Id": "restarted-page-identity", "X-Controller-Token": token}
            result = restarted.get("/api/selections", params=self.query, headers=headers).json()
            self.assertEqual(result["selections"][0]["start"], 19.75)
            removed = restarted.delete("/api/selections/manual-range-identity", params=self.query, headers={**headers, "If-Match": result["revision"]})
            self.assertEqual(removed.status_code, 200)
            self.assertEqual(json.loads(self.path.read_text())["selections"], [])

    def test_selection_order_is_filename_then_timestamp(self):
        make_project(self.root, self.project, "Z.mp4")
        for index, (file, start) in enumerate([("Z.mp4", 10), (self.file, 30), (self.file, 5)]):
            response = self.client.post("/api/selections", params=self.query, headers=self.headers,
                                        json={"id": f"sort-identity-{index:016}", "file": file, "start": start, "end": start + 2})
            self.assertEqual(response.status_code, 201)
        self.assertEqual([(row["file"], row["start"]) for row in response.json()["selections"]], [(self.file, 5), (self.file, 30), ("Z.mp4", 10)])

    def test_duplicate_capture_id_is_idempotent(self):
        self.assertEqual(self.capture().status_code, 201)
        self.assertEqual(len(self.capture().json()["selections"]), 1)
        self.assertEqual(self.capture(60).status_code, 409)

    def test_invalid_ranges_never_create_metadata(self):
        for start, end in [(2, 2), (4, 1), (-1, 5), (0, 121), (True, 3), ("1", 3)]:
            response = self.client.post("/api/selections", params=self.query, headers=self.headers,
                                        json={"id": "invalid-range-identity", "file": self.file, "start": start, "end": end})
            self.assertEqual(response.status_code, 422)
        response = self.client.post("/api/selections", params=self.query, headers={**self.headers, "Content-Type": "application/json"},
                                    content=json.dumps({"id": "invalid-range-identity", "file": self.file, "start": 0, "end": float("inf")}))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.capture(999).status_code, 422)
        self.assertFalse(self.path.parent.exists())

    def test_stale_revision_blocks_edit_and_delete(self):
        result = self.capture().json()
        before = self.path.read_bytes()
        for method in ["patch", "delete"]:
            arguments = {"params": self.query, "headers": {**self.headers, "If-Match": "stale"}}
            if method == "patch": arguments["json"] = {"start": 1, "end": 2}
            response = getattr(self.client, method)("/api/selections/capture-identity-1234", **arguments)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(self.path.read_bytes(), before)
        self.assertNotEqual(result["revision"], "stale")

    def test_missing_and_case_renamed_media_stays_unavailable(self):
        self.capture()
        original = self.root / self.project / self.file
        renamed = original.with_name("replacement.mp4")
        original.rename(renamed)
        response = self.client.get("/api/selections", params=self.query, headers=self.headers)
        self.assertFalse(response.json()["selections"][0]["available"])
        self.assertEqual(response.json()["selections"][0]["file"], self.file)
        # Even if the filesystem would match it case-insensitively, don't reattach.
        renamed.rename(original.with_name(self.file.upper()))
        self.assertFalse(self.client.get("/api/selections", params=self.query, headers=self.headers).json()["selections"][0]["available"])
        revision = response.json()["revision"]
        self.assertEqual(self.client.delete("/api/selections/capture-identity-1234", params=self.query, headers={**self.headers, "If-Match": revision}).status_code, 200)

    def test_atomic_replacement_failure_leaves_old_data_and_source_intact(self):
        folder = self.root / self.project
        (folder / "Source").mkdir()
        original = folder / "Source" / "download.mkv"
        original.write_bytes(b"original")
        self.capture()
        manifest = self.path.parent / "manifest.json"
        manifest.write_bytes(b'{"owned_by":"processor"}')
        watched = [self.path, folder / self.file, original, manifest]
        before = [path.read_bytes() for path in watched]
        with self.assertLogs("uvicorn.error", level="ERROR"), patch("pocket_clip_selector.storage.os.replace", side_effect=OSError("simulated disk failure")):
            response = self.capture(60, "failed-capture-identity")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "storage_error")
        self.assertEqual([path.read_bytes() for path in watched], before)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_fsync_failure_preserves_old_data(self):
        self.capture()
        old = self.path.read_bytes()
        with self.assertLogs("uvicorn.error", level="ERROR"), patch("pocket_clip_selector.storage.os.fsync", side_effect=OSError("simulated failure")):
            self.assertEqual(self.capture(70, "fsync-failure-identity").status_code, 500)
        self.assertEqual(self.path.read_bytes(), old)

    def test_corrupt_or_unsupported_storage_never_overwritten(self):
        self.path.parent.mkdir()
        for payload in [b"", b"not json", b'{"version":2,"selections":[]}', b'{"version":1,"selections":[{}]}']:
            self.path.write_bytes(payload)
            self.assertEqual(self.capture().status_code, 500)
            self.assertEqual(self.path.read_bytes(), payload)

    def test_path_traversal_absolute_subfolder_and_stream_extension_blocked(self):
        for project, file in [("..", self.file), ("../escape", self.file), ("/tmp", self.file), ("D:\\outside", self.file),
                              (self.project, "../outside.mp4"), (self.project, "Source/nested.mp4"), (self.project, "D:\\outside.mp4"),
                              (self.project, "original.mkv"), (self.project, "movie.mp4:stream")]:
            with self.subTest(project=project, file=file):
                response = self.client.get("/media", params={"project": project, "file": file})
                self.assertEqual(response.status_code, 400)
        for project in ["..", "../escape", "/tmp", "D:\\outside"]:
            self.assertEqual(self.client.get("/api/selections", params={"project": project}, headers=self.headers).status_code, 400)

    def test_symlink_projects_media_metadata_and_destination_are_blocked(self):
        outside = Path(self.temporary.name).resolve() / "outside"
        outside.mkdir()
        (outside / "secret.mp4").write_bytes(mp4_bytes())
        try:
            (self.root / "link-project").symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks need Developer Mode or elevation on this Windows machine.")
        folder = self.root / self.project
        (folder / "linked.mp4").symlink_to(outside / "secret.mp4")
        self.assertEqual(self.client.get("/media", params={"project": "link-project", "file": "secret.mp4"}).status_code, 400)
        self.assertEqual(self.client.get("/media", params={**self.query, "file": "linked.mp4"}).status_code, 400)
        (folder / ".clipselector").symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.capture().status_code, 400)
        self.assertFalse((outside / "selections.json").exists())
        (folder / ".clipselector").unlink()
        self.path.parent.mkdir()
        secret = outside / "selections.json"
        secret.write_text('{"version":1,"selections":[]}', encoding="utf-8")
        self.path.symlink_to(secret)
        self.assertEqual(self.capture().status_code, 400)
        self.assertEqual(secret.read_text(), '{"version":1,"selections":[]}')
        names = [item["name"] for item in self.client.get("/api/projects", headers=self.headers).json()["projects"]]
        self.assertNotIn("link-project", names)

    @unittest.skipUnless(os.name == "nt", "Windows junction test runs on the target PC")
    def test_windows_junction_is_blocked(self):
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        junction = self.root / "junction"
        subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(outside)], check=True, capture_output=True)
        try:
            self.assertEqual(self.client.get("/api/project", params={"project": "junction"}, headers=self.headers).status_code, 400)
        finally:
            junction.rmdir()

    def test_all_library_access_requires_control_except_stream_and_static(self):
        for path in ["/api/projects", "/api/project", "/api/selections", "/api/media-info"]:
            response = self.client.get(path, params={**self.query, "file": self.file})
            self.assertEqual(response.status_code, 423)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/assets/app.js").status_code, 200)
        self.assertEqual(self.client.get("/media", params={**self.query, "file": self.file}, headers={"Range": "bytes=0-1"}).status_code, 206)

    def test_home_screen_manifest_and_icons_are_public(self):
        response = self.client.get("/assets/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/manifest+json")
        manifest = response.json()
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["scope"], "/")
        for icon in manifest["icons"]:
            response = self.client.get(icon["src"])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], icon["type"])
        self.assertTrue(self.client.get("/assets/apple-touch-icon.png").content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_first_page_acquires_control_without_timers(self):
        self.assertTrue(self.token)
        self.assertEqual(self.client.get("/api/projects", headers=self.headers).status_code, 200)
        result = self.client.post("/api/controller/claim", json={"page_id": self.page}).json()
        self.assertEqual(set(result), {"token"})
        self.assertEqual(self.client.post("/api/controller/heartbeat", json={"page_id": self.page, "token": result["token"]}).status_code, 404)

    def test_second_page_cannot_claim_read_or_mutate_without_takeover(self):
        other = "second-page-identity-1234"
        self.assertEqual(self.client.post("/api/controller/claim", json={"page_id": other}).status_code, 423)
        bad = {"X-Page-Id": other, "X-Controller-Token": self.token}
        self.assertEqual(self.client.get("/api/projects", headers=bad).status_code, 423)
        self.assertEqual(self.client.post("/api/selections/capture", params=self.query, headers=bad,
                                        json={"file": self.file, "time": 2, "id": "other-capture-identity"}).status_code, 423)
        self.assertFalse(self.path.exists())

    def test_takeover_invalidates_every_previous_mutation_and_release(self):
        result = self.capture().json()
        before = self.path.read_bytes()
        other = "second-page-identity-1234"
        token = self.client.post("/api/controller/takeover", json={"page_id": other}).json()["token"]
        stale = [
            self.capture(identity="stale-capture-identity"),
            self.client.post("/api/selections", params=self.query, headers=self.headers,
                             json={"id": "stale-manual-identity", "file": self.file, "start": 1, "end": 2}),
            self.client.patch("/api/selections/capture-identity-1234", params=self.query,
                              headers={**self.headers, "If-Match": result["revision"]}, json={"start": 1, "end": 2}),
            self.client.delete("/api/selections/capture-identity-1234", params=self.query,
                               headers={**self.headers, "If-Match": result["revision"]}),
            self.client.post("/api/controller/release", json={"page_id": self.page, "token": self.token}),
        ]
        for response in stale:
            self.assertEqual(response.status_code, 423)
            self.assertEqual(response.json()["error"]["code"], "controller_transferred")
            self.assertEqual(response.json()["error"]["message"], "Editor control was transferred to another page")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.client.post("/api/controller/claim", json={"page_id": self.page}).status_code, 423)
        self.assertEqual(self.client.get("/api/projects", headers={"X-Page-Id": other, "X-Controller-Token": token}).status_code, 200)
        self.assertEqual(self.client.get("/media", params={**self.query, "file": self.file}, headers={"Range": "bytes=0-1"}).status_code, 206)

    def test_ownership_survives_arbitrary_time_without_requests(self):
        for now in [0, 15, 86400, 10**12]:
            with patch("time.monotonic", return_value=now), patch("time.time", return_value=now):
                with self.controller.authorized(self.page, self.token):
                    self.assertEqual(self.controller.page, self.page)
        self.assertEqual(self.client.post("/api/controller/claim", json={"page_id": "later-page-identity-1234"}).status_code, 423)
        self.assertEqual(self.capture().status_code, 201)

    def test_explicit_release_allows_another_page_to_claim(self):
        self.assertEqual(self.client.post("/api/controller/release", json={"page_id": self.page, "token": self.token}).status_code, 200)
        self.assertEqual(self.capture().status_code, 409)
        self.assertEqual(self.client.post("/api/controller/claim", json={"page_id": "another-page-identity"}).status_code, 200)
        self.assertEqual(self.client.post("/api/controller/release", json={"page_id": self.page, "token": self.token}).status_code, 423)

    def test_reentering_editor_invalidates_old_token(self):
        self.assertEqual(self.client.post("/api/controller/release", json={"page_id": self.page, "token": self.token}).status_code, 200)
        reclaimed = self.client.post("/api/controller/claim", json={"page_id": self.page}).json()["token"]
        self.assertNotEqual(reclaimed, self.token)
        self.assertEqual(self.client.post("/api/controller/release", json={"page_id": self.page, "token": self.token}).status_code, 423)
        self.headers["X-Controller-Token"] = reclaimed
        self.assertEqual(self.capture().status_code, 201)

    def test_restart_clears_control_and_rejects_previous_token(self):
        with TestClient(create_app(Settings(self.root), lock_library=False)) as restarted:
            self.assertEqual(restarted.get("/api/projects", headers=self.headers).status_code, 409)
            token = restarted.post("/api/controller/claim", json={"page_id": "new-page-after-restart"}).json()["token"]
            self.assertEqual(restarted.get("/api/projects", headers={"X-Page-Id": "new-page-after-restart", "X-Controller-Token": token}).status_code, 200)
            self.assertEqual(restarted.post("/api/selections/capture", params=self.query, headers=self.headers,
                                            json={"id": "stale-restart-capture", "file": self.file, "time": 10}).status_code, 423)
        self.assertFalse(self.path.exists())

    def test_takeover_waits_for_in_flight_durable_write(self):
        writing, commit, transferring = threading.Event(), threading.Event(), threading.Event()
        order = []
        original_write, original_claim = self.app.state.store._write, self.controller.claim
        def held_write(*args):
            writing.set()
            if not commit.wait(5): raise AssertionError("Test did not allow the write to finish")
            result = original_write(*args)
            order.append("write")
            return result
        def observed_claim(*args, **kwargs):
            transferring.set()
            result = original_claim(*args, **kwargs)
            order.append("takeover")
            return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            with patch.object(self.app.state.store, "_write", held_write), patch.object(self.controller, "claim", observed_claim):
                pending_write = pool.submit(self.capture)
                try:
                    self.assertTrue(writing.wait(5))
                    pending_takeover = pool.submit(self.client.post, "/api/controller/takeover", json={"page_id": "concurrent-new-controller"})
                    self.assertTrue(transferring.wait(5))
                    self.assertFalse(pending_takeover.done(), "Takeover must wait for the durable mutation")
                finally:
                    commit.set()
                self.assertEqual(pending_write.result(timeout=5).status_code, 201)
                takeover = pending_takeover.result(timeout=5)
                self.assertEqual(takeover.status_code, 200)
        self.assertEqual(order, ["write", "takeover"])
        self.assertEqual(self.capture(identity="stale-after-transfer").status_code, 423)
        response = self.client.post("/api/selections/capture", params=self.query,
                                    headers={"X-Page-Id": "concurrent-new-controller", "X-Controller-Token": takeover.json()["token"]},
                                    json={"id": "new-controller-capture", "file": self.file, "time": 80})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(json.loads(self.path.read_text())["selections"]), 2)

    def test_queued_stale_write_cannot_commit_after_completed_takeover(self):
        waiting = threading.Event()
        original_access = self.controller.authorized
        def observed_access(page, token):
            waiting.set()
            return original_access(page, token)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(self.controller, "authorized", observed_access):
                with self.controller.lock:
                    pending = pool.submit(self.capture)
                    self.assertTrue(waiting.wait(5))
                    self.controller.claim("controller-before-queued-save", takeover=True)
                self.assertEqual(pending.result(timeout=5).status_code, 423)
        self.assertFalse(self.path.exists())

    def test_foreign_origin_is_rejected_and_input_errors_are_json(self):
        self.assertEqual(self.client.post("/api/controller/claim", json={"page_id": self.page}, headers={"Origin": "https://other.example"}).status_code, 403)
        response = self.client.post("/api/controller/claim", json={"page_id": 123})
        self.assertEqual(response.status_code, 422)
        self.assertIn("error", response.json())
        self.assertEqual(self.client.get("/assets/not-an-asset").status_code, 404)

    def test_concurrent_server_mutations_keep_every_selection(self):
        store = self.app.state.store
        def add(index):
            return store.add(self.project, {"id": f"parallel-identity-{index:016}", "file": self.file, "start": index, "end": index + 1})
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(add, range(12)))
        records = json.loads(self.path.read_text())["selections"]
        self.assertEqual(len(records), 12)
        self.assertEqual(len({record["id"] for record in records}), 12)


class InfrastructureTests(unittest.TestCase):
    def test_case_insensitive_sort_has_deterministic_tie_breaker(self):
        self.assertEqual(sorted(["b.mp4", "a.mp4", "A.mp4", "B.mp4"], key=sort_key), ["A.mp4", "a.mp4", "B.mp4", "b.mp4"])

    def test_mp4_duration_version_zero_one_extended_and_moov_after_data(self):
        for version in [0, 1]:
            for tail in [False, True]:
                for extended in [False, True]:
                    data = mp4_bytes(123.456, version=version, tail=tail, extended=extended)
                    self.assertEqual(duration(io.BytesIO(data), len(data)), 123.456)

    def test_invalid_movie_header_is_rejected(self):
        for data in [b"", b"not an mp4", mp4_bytes(0), b"\0\0\0\1moov"]:
            with self.assertRaises(AppError): duration(io.BytesIO(data), len(data))

    def test_duration_skips_large_media_payload_without_loading_it(self):
        class TrackingStream(io.BytesIO):
            biggest_read = 0
            def read(self, size=-1):
                self.biggest_read = max(self.biggest_read, size)
                return super().read(size)
        data = mp4_bytes(123.456, tail=True)
        stream = TrackingStream(data)
        self.assertEqual(duration(stream, len(data)), 123.456)
        self.assertLessEqual(stream.biggest_read, 32)

    def test_process_lock_rejects_duplicates_and_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            first, second = ProcessLock(Path(folder)), ProcessLock(Path(folder))
            first.acquire()
            try:
                with self.assertRaises(RuntimeError): second.acquire()
            finally: first.close()
            second.acquire()
            second.close()

    def test_env_absolute_paths_unicode_and_environment_override(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve() / "媒体 with spaces"
            root.mkdir()
            env = Path(folder) / ".env"
            env.write_text(f'WORKING_DIR="{root}"\nHOST=0.0.0.0\nPORT=8767\n', encoding="utf-8-sig")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(load_settings(env).working_dir, root)
                self.assertEqual(load_settings(env).port, 8767)
                with patch.dict(os.environ, {"PORT": "9876"}): self.assertEqual(load_settings(env).port, 9876)
                for value in ["0", "65536", "abc"]:
                    with patch.dict(os.environ, {"PORT": value}):
                        with self.assertRaises(ValueError): load_settings(env)
                with patch.dict(os.environ, {"WORKING_DIR": "relative/path"}):
                    with self.assertRaises(ValueError): load_settings(env)

    def test_repo_and_library_must_be_separate(self):
        with tempfile.TemporaryDirectory() as folder:
            env = Path(folder) / ".env"
            env.write_text(f"WORKING_DIR={Path(__file__).resolve().parents[1]}", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError): load_settings(env)
