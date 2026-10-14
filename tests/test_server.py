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
from pocket_clip_selector.storage import CATEGORIES, MAX_SECONDS, source_key, source_name, next_episode, following_episode
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
        self.source = "Episode 01"
        self.path = self.root / self.project / ".clipselector" / "project.json"

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temporary.cleanup()

    def snapshot(self):
        response = self.client.get("/api/project", params=self.query, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def revision(self):
        return {**self.headers, "If-Match": self.snapshot()["revision"]}

    def prepare(self, category="Anime", file=None):
        response = self.client.post("/api/project/initialize", params=self.query, headers=self.revision(), json={"category": category})
        self.assertEqual(response.status_code, 200, response.text)
        response = self.add_source(self.source, file)
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def add_source(self, name, file=None):
        return self.client.post("/api/sources", params=self.query, headers=self.revision(), json={"name": name, "media_file": file})

    def bookmark(self, time=50.125, identity="bookmark-identity-1234", source=None, headers=None):
        return self.client.post("/api/bookmarks", params={**self.query, "source": source or self.source}, headers=headers or self.headers, json={"time": time, "id": identity})

    def test_project_creation_categories_status_and_listing_counts(self):
        for index, category in enumerate(CATEGORIES):
            with self.subTest(category=category):
                response = self.client.post("/api/projects", headers=self.headers, json={"name": f"新 Project {index}", "category": category})
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()["category"], category)
                self.assertEqual(response.json()["status"], "Discovering")
                self.assertEqual(response.json()["next_source_name"], "Episode 01")
                self.assertEqual(response.json()["media"], [])
        self.prepare()
        self.bookmark()
        updated = self.client.patch("/api/project", params=self.query, headers=self.revision(), json={"status": "Editing"})
        self.assertEqual(updated.status_code, 200)
        rows = self.client.get("/api/projects", headers=self.headers).json()["projects"]
        row = next(row for row in rows if row["name"] == self.project)
        self.assertEqual((row["category"], row["status"], row["source_count"], row["bookmark_count"]), ("Anime", "Editing", 1, 1))
        self.assertEqual(self.client.patch("/api/project", params=self.query, headers=self.revision(), json={"status": "Completed"}).status_code, 422)

    def test_creation_rejects_unsafe_names_categories_and_collisions(self):
        for name in ["", "..", "../escape", "/tmp", "D:\\outside", "bad?name", "CON", "aux.txt", "LPT1", "end.", "x"*101, "a\x00b"]:
            with self.subTest(name=name):
                self.assertIn(self.client.post("/api/projects", headers=self.headers, json={"name": name, "category": "Anime"}).status_code, [400, 422])
        before = list(self.root.iterdir())
        self.assertEqual(self.client.post("/api/projects", headers=self.headers, json={"name": "Nope", "category": "Music"}).status_code, 422)
        self.assertEqual(list(self.root.iterdir()), before)
        for name in [self.project, self.project.upper()]:
            self.assertEqual(self.client.post("/api/projects", headers=self.headers, json={"name": name, "category": "Anime"}).status_code, 409)

    def test_external_folder_initialization_preserves_media_processor_files(self):
        folder = self.root / self.project
        (folder / "Source").mkdir()
        original = folder / "Source" / "stream.mkv"; original.write_bytes(b"original")
        self.path.parent.mkdir()
        manifest = self.path.parent / "manifest.json"; manifest.write_bytes(b'{"processor":true}')
        old_metadata = self.path.parent / "selections.json"; old_metadata.write_bytes(b"obsolete and ignored")
        watched = [folder / self.file, original, manifest, old_metadata]
        before = [path.read_bytes() for path in watched]
        self.assertFalse(self.snapshot()["initialized"])
        self.prepare()
        self.assertEqual([path.read_bytes() for path in watched], before)
        self.assertEqual(self.client.post("/api/project/initialize", params=self.query, headers=self.revision(), json={"category": "Donghua"}).status_code, 409)

    def test_discovery_is_nonrecursive_and_new_folders_need_no_manifest(self):
        (self.root / "Empty").mkdir()
        folder = self.root / self.project
        for name in ["Source", ".clipselector", "Nested"]:
            nested = folder / name; nested.mkdir(); (nested / "ignored.mp4").write_bytes(mp4_bytes())
        (folder / "original.mkv").write_bytes(b"original")
        (folder / "B.MP4").write_bytes(mp4_bytes())
        media = self.snapshot()["media"]
        self.assertEqual([row["name"] for row in media], sorted([self.file, "B.MP4"], key=sort_key))
        empty = self.client.get("/api/project", params={"project":"Empty"}, headers=self.headers).json()
        self.assertFalse(empty["initialized"]); self.assertEqual(empty["sources"], [])
        self.assertFalse((self.root / "Empty" / ".clipselector").exists())

    def test_source_names_for_all_categories_and_sequential_defaults(self):
        for category in CATEGORIES:
            project = self.client.post("/api/projects", headers=self.headers, json={"name": category, "category": category}).json()
            self.assertEqual(project["next_source_name"], "Episode 01")
            for name, next_name in [("Episode 01", "Episode 02"), ("ep02", "Episode 03"), ("OVA 1", "Episode 03")]:
                response = self.client.post("/api/sources", params={"project": category}, headers={**self.headers,"If-Match": project["revision"]}, json={"name": name})
                self.assertEqual(response.status_code, 201, response.text)
                project = response.json(); self.assertEqual(project["next_source_name"], next_name)

    def test_duplicate_create_and_rename_point_to_existing_source(self):
        self.prepare()
        self.add_source("Episode 07")
        self.add_source("OVA 1")
        self.add_source("Season 2 - Episode 1")
        for name in ["episode 07", " Episode   07 ", "Episode 7", "EP 7", "ep07", "Episode 007"]:
            with self.subTest(name=name):
                response = self.add_source(name)
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.json()["error"]["source"], "Episode 07")
                renamed = self.client.patch("/api/source", params={**self.query,"source":"OVA 1"}, headers=self.revision(), json={"name":name,"media_file":None})
                self.assertEqual(renamed.status_code, 409)
                self.assertEqual(renamed.json()["error"]["source"], "Episode 07")
        self.assertEqual(self.add_source("ova   1").status_code, 409)
        self.assertEqual(self.add_source("__proto__").status_code, 201)
        for name in [" ", "a"*101, "a\x00b", "a\nb"]:
            self.assertEqual(self.add_source(name).status_code, 422)

    def test_bookmarks_without_media_sorted_edited_deleted_and_restarted(self):
        (self.root / self.project / self.file).unlink()
        self.prepare()
        for index, time in enumerate([1062, 0, 1061.999, 1062, 50000]):
            response = self.bookmark(time, f"bookmark-{index:016}")
            self.assertEqual(response.status_code, 201, response.text)
        marks = self.snapshot()["sources"][0]["bookmarks"]
        self.assertEqual([row["time"] for row in marks], [0,1061.999,1062,1062,50000])
        self.assertTrue(all(set(row)=={"id","time"} for row in marks))
        changed = self.client.patch(f'/api/bookmarks/{marks[0]["id"]}', params={**self.query,"source":self.source}, headers=self.revision(), json={"time":42})
        self.assertEqual(changed.status_code, 200)
        with TestClient(create_app(Settings(self.root),lock_library=False)) as restarted:
            token = restarted.post("/api/controller/claim",json={"page_id":"restarted-page-identity"}).json()["token"]
            headers = {"X-Page-Id":"restarted-page-identity","X-Controller-Token":token}
            result = restarted.get("/api/project",params=self.query,headers=headers).json()
            self.assertEqual(result["sources"][0]["bookmarks"][0]["time"],42)
            self.assertEqual(restarted.delete(f'/api/bookmarks/{marks[0]["id"]}',params={**self.query,"source":self.source},headers={**headers,"If-Match":result["revision"]}).status_code,200)
        self.assertEqual(len(json.loads(self.path.read_text())["sources"][self.source]["bookmarks"]),4)

    def test_invalid_bookmark_values_and_obsolete_endpoints(self):
        self.prepare(); before=self.path.read_bytes()
        for time in [-1,True,"1742",None,MAX_SECONDS+1]:
            self.assertEqual(self.bookmark(time).status_code,422)
        for time in [float("nan"),float("inf")]:
            response=self.client.post("/api/bookmarks",params={**self.query,"source":self.source},headers={**self.headers,"Content-Type":"application/json"},content=json.dumps({"id":"invalid-bookmark-id","time":time}))
            self.assertEqual(response.status_code,422)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.bookmark(MAX_SECONDS).status_code,201)
        self.assertEqual(self.client.post("/api/selections",params=self.query,headers=self.headers,json={}).status_code,404)
        self.assertEqual(self.client.post("/api/bookmarks",params={**self.query,"source":self.source},headers=self.headers,json={"id":"no-range-identity","time":1,"start":0,"end":2}).status_code,422)

    def test_repeated_bookmark_requests_are_idempotent_but_nearby_times_are_kept(self):
        self.prepare()
        first=self.bookmark().json()
        self.assertEqual(self.bookmark().json()["revision"],first["revision"])
        self.assertEqual(self.bookmark(60).status_code,409)
        self.assertEqual(self.bookmark(50.126,"nearby-bookmark-id").status_code,201)
        self.assertEqual(self.snapshot()["bookmark_count"],2)

    def test_rename_association_reassociation_and_remove_preserve_physical_media(self):
        self.prepare(); self.bookmark()
        response=self.client.patch("/api/source",params={**self.query,"source":self.source},headers=self.revision(),json={"name":"OVA 1","media_file":self.file})
        self.assertEqual(response.status_code,200)
        original=(self.root/self.project/self.file).read_bytes()
        make_project(self.root,self.project,"Next.mp4")
        changed=self.client.patch("/api/source",params={**self.query,"source":"OVA 1"},headers=self.revision(),json={"name":"Movie","media_file":"Next.mp4"})
        self.assertEqual(changed.status_code,200)
        row=changed.json()["sources"][0]
        self.assertTrue(row["available"]); self.assertEqual(row["bookmarks"][0]["time"],50.125)
        self.assertEqual(self.client.delete("/api/source",params={**self.query,"source":"Movie"},headers=self.revision()).status_code,200)
        self.assertEqual((self.root/self.project/self.file).read_bytes(),original)
        self.assertTrue((self.root/self.project/"Next.mp4").exists())
        self.assertEqual(self.snapshot()["sources"],[])

    def test_missing_association_does_not_block_manual_bookmarks_or_rename(self):
        self.prepare(file=self.file); self.bookmark()
        path=self.root/self.project/self.file; path.rename(path.with_name(self.file.upper()))
        self.assertFalse(self.snapshot()["sources"][0]["available"])
        self.assertEqual(self.bookmark(999,"missing-media-bookmark").status_code,201)
        renamed=self.client.patch("/api/source",params={**self.query,"source":self.source},headers=self.revision(),json={"name":"Part 1","media_file":self.file})
        self.assertEqual(renamed.status_code,200); self.assertEqual(renamed.json()["bookmark_count"],2)
        self.assertEqual(renamed.json()["sources"][0]["media_file"],self.file)

    def test_partial_source_changes_preserve_omitted_name_or_association(self):
        self.prepare(file=self.file)
        self.bookmark()
        renamed = self.client.patch("/api/source", params={**self.query, "source": self.source}, headers=self.revision(), json={"name": "Movie"})
        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["sources"][0]["media_file"], self.file)
        unlinked = self.client.patch("/api/source", params={**self.query, "source": "Movie"}, headers=self.revision(), json={"media_file": None})
        self.assertEqual(unlinked.status_code, 200)
        row = unlinked.json()["sources"][0]
        self.assertEqual(row["name"], "Movie")
        self.assertIsNone(row["media_file"])
        self.assertEqual(row["bookmarks"][0]["time"], 50.125)

    def test_unsafe_associations_and_project_paths_are_rejected(self):
        self.prepare()
        for file in ["../outside.mp4","Source/nested.mp4","D:\\outside.mp4","original.mkv","movie.mp4:stream","/tmp/movie.mp4"]:
            self.assertEqual(self.add_source("Episode 02",file).status_code,400)
            self.assertEqual(self.client.get("/media",params={**self.query,"file":file}).status_code,400)
        for project in ["..","../escape","/tmp","D:\\outside"]:
            self.assertEqual(self.client.get("/api/project",params={"project":project},headers=self.headers).status_code,400)
        self.assertEqual(self.add_source("Missing","missing.mp4").status_code,404)

    def test_stale_revision_blocks_every_destructive_change(self):
        self.prepare(); self.bookmark(); before=self.path.read_bytes()
        query={**self.query,"source":self.source}; stale={**self.headers,"If-Match":"stale"}
        responses=[self.client.patch("/api/project",params=self.query,headers=stale,json={"status":"Editing"}),
          self.client.post("/api/sources",params=self.query,headers=stale,json={"name":"Another"}),
          self.client.patch("/api/source",params=query,headers=stale,json={"name":"Rename","media_file":None}),
          self.client.delete("/api/source",params=query,headers=stale),
          self.client.patch("/api/bookmarks/bookmark-identity-1234",params=query,headers=stale,json={"time":1}),
          self.client.delete("/api/bookmarks/bookmark-identity-1234",params=query,headers=stale)]
        for response in responses:self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.path.read_bytes(),before)

    def test_atomic_failure_and_fsync_failure_preserve_project_media_and_manifest(self):
        self.prepare(); self.bookmark()
        manifest=self.path.parent/"manifest.json"; manifest.write_bytes(b'{"processor":true}')
        files=[self.path,self.root/self.project/self.file,manifest]; before=[path.read_bytes() for path in files]
        for operation in ["os.replace","os.fsync"]:
            with self.assertLogs("uvicorn.error",level="ERROR"),patch(f"pocket_clip_selector.storage.{operation}",side_effect=OSError("disk failure")):
                self.assertEqual(self.bookmark(70,"failed-bookmark-id").status_code,500)
            self.assertEqual([path.read_bytes() for path in files],before)
            self.assertEqual(list(self.path.parent.glob(".*.tmp")),[])

    def test_damaged_metadata_is_not_overwritten_and_other_projects_are_browseable(self):
        self.path.parent.mkdir()
        for payload in [b"",b"not json",b'{"version":2}',b'{"version":1,"category":"Anime","status":"Discovering","sources":{"EP1":{"media_file":null,"bookmarks":[]},"Episode 01":{"media_file":null,"bookmarks":[]}}}',b'{"version":1,"category":"Anime","status":"Discovering","sources":{},"sources":{}}']:
            self.path.write_bytes(payload)
            self.assertEqual(self.client.get("/api/project",params=self.query,headers=self.headers).status_code,500)
            response=self.client.post("/api/project/initialize",params=self.query,headers={**self.headers,"If-Match":"anything"},json={"category":"Anime"})
            self.assertEqual(response.status_code,500); self.assertEqual(self.path.read_bytes(),payload)
            rows=self.client.get("/api/projects",headers=self.headers).json()["projects"]
            self.assertIn("error",next(row for row in rows if row["name"]==self.project))

    def test_external_change_during_write_is_detected_before_replacement(self):
        self.prepare()
        changed = json.loads(self.path.read_text())
        changed["status"] = "Editing"
        payload = json.dumps(changed).encode("utf-8")
        with patch("pocket_clip_selector.storage.os.fsync", side_effect=lambda descriptor: self.path.write_bytes(payload)):
            response = self.bookmark()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.path.read_bytes(), payload)
        self.assertEqual(list(self.path.parent.glob(".*.tmp")), [])

    def test_failed_new_project_write_can_be_initialized_without_deleting_folder(self):
        with self.assertLogs("uvicorn.error", level="ERROR"), patch("pocket_clip_selector.storage.os.replace", side_effect=OSError("disk failure")):
            response = self.client.post("/api/projects", headers=self.headers, json={"name": "Recoverable", "category": "Anime"})
        self.assertEqual(response.status_code, 500)
        snapshot = self.client.get("/api/project", params={"project": "Recoverable"}, headers=self.headers).json()
        self.assertFalse(snapshot["initialized"])
        self.assertTrue((self.root / "Recoverable").is_dir())
        response = self.client.post("/api/project/initialize", params={"project": "Recoverable"}, headers={**self.headers, "If-Match": snapshot["revision"]}, json={"category": "Anime"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["initialized"])

    def test_symlink_projects_media_metadata_and_destination_are_blocked(self):
        outside=Path(self.temporary.name).resolve()/"outside"; outside.mkdir(); (outside/"secret.mp4").write_bytes(mp4_bytes())
        try: (self.root/"link-project").symlink_to(outside,target_is_directory=True)
        except OSError: self.skipTest("Symlinks require Windows Developer Mode or elevation.")
        folder=self.root/self.project; (folder/"linked.mp4").symlink_to(outside/"secret.mp4")
        self.assertEqual(self.client.get("/media",params={"project":"link-project","file":"secret.mp4"}).status_code,400)
        self.assertEqual(self.client.get("/media",params={**self.query,"file":"linked.mp4"}).status_code,400)
        (folder/".clipselector").symlink_to(outside,target_is_directory=True)
        self.assertEqual(self.client.get("/api/project",params=self.query,headers=self.headers).status_code,400)
        (folder/".clipselector").unlink(); self.path.parent.mkdir()
        secret=outside/"project.json"; secret.write_bytes(b"private"); self.path.symlink_to(secret)
        self.assertEqual(self.client.get("/api/project",params=self.query,headers=self.headers).status_code,400)
        self.assertEqual(secret.read_bytes(),b"private")
        self.assertFalse((outside/"manifest.json").exists())
        self.assertNotIn("link-project",[row["name"] for row in self.client.get("/api/projects",headers=self.headers).json()["projects"]])

    def test_all_library_and_mutation_routes_require_controller(self):
        for path in ["/api/projects","/api/project","/api/media-info"]:
            self.assertEqual(self.client.get(path,params={**self.query,"file":self.file}).status_code,423)
        self.assertEqual(self.client.post("/api/projects",json={"name":"Blocked","category":"Anime"}).status_code,423)
        self.assertEqual(self.client.get("/").status_code,200)
        self.assertEqual(self.client.get("/media",params={**self.query,"file":self.file},headers={"Range":"bytes=0-1"}).status_code,206)

    def test_manual_ownership_claim_takeover_release_and_restart(self):
        self.prepare(); self.bookmark(); before=self.path.read_bytes()
        other="second-page-identity-1234"
        self.assertEqual(self.client.post("/api/controller/claim",json={"page_id":other}).status_code,423)
        token=self.client.post("/api/controller/takeover",json={"page_id":other}).json()["token"]
        self.assertEqual(self.bookmark(60,"stale-bookmark-id").status_code,423)
        query={**self.query,"source":self.source}
        for response in [self.client.patch("/api/source",params=query,headers=self.headers,json={"name":"Rename"}),self.client.delete("/api/source",params=query,headers=self.headers),self.client.post("/api/controller/release",json={"page_id":self.page,"token":self.token})]:self.assertEqual(response.status_code,423)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.client.post("/api/controller/release",json={"page_id":other,"token":token}).status_code,200)
        claimed=self.client.post("/api/controller/claim",json={"page_id":self.page}).json()["token"]
        self.assertNotEqual(claimed,self.token)
        self.headers["X-Controller-Token"]=claimed
        self.assertEqual(self.bookmark(60,"new-bookmark-identity").status_code,201)
        with TestClient(create_app(Settings(self.root),lock_library=False)) as restarted:
            self.assertEqual(restarted.get("/api/project",params=self.query,headers=self.headers).status_code,409)
            token=restarted.post("/api/controller/claim",json={"page_id":other}).json()["token"]
            self.assertEqual(restarted.get("/api/project",params=self.query,headers=self.headers).status_code,423)
        self.assertEqual(self.client.post("/api/controller/heartbeat",json={}).status_code,404)

    def test_ownership_does_not_expire_and_transfer_waits_for_durable_write(self):
        self.prepare()
        for now in [0,15,86400,10**12]:
            with patch("time.monotonic",return_value=now),patch("time.time",return_value=now):
                with self.controller.authorized(self.page,self.token):self.assertEqual(self.controller.page,self.page)
        writing,commit,transferring=threading.Event(),threading.Event(),threading.Event(); order=[]
        original_write,original_claim=self.app.state.store._write,self.controller.claim
        def held_write(*args):
            writing.set()
            if not commit.wait(5):raise AssertionError("Write did not resume")
            result=original_write(*args); order.append("write"); return result
        def observed_claim(*args,**kwargs):
            transferring.set(); result=original_claim(*args,**kwargs); order.append("takeover"); return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            with patch.object(self.app.state.store,"_write",held_write),patch.object(self.controller,"claim",observed_claim):
                pending=pool.submit(self.bookmark)
                try:
                    self.assertTrue(writing.wait(5)); takeover=pool.submit(self.client.post,"/api/controller/takeover",json={"page_id":"next-controller-identity"})
                    self.assertTrue(transferring.wait(5)); self.assertFalse(takeover.done())
                finally:commit.set()
                self.assertEqual(pending.result(timeout=5).status_code,201); self.assertEqual(takeover.result(timeout=5).status_code,200)
        self.assertEqual(order,["write","takeover"])
        self.assertEqual(self.bookmark(70,"after-transfer-bookmark").status_code,423)

    def test_queued_stale_write_cannot_commit_after_takeover(self):
        self.prepare(); before=self.path.read_bytes(); waiting=threading.Event(); original=self.controller.authorized
        def observed(page,token):waiting.set(); return original(page,token)
        with ThreadPoolExecutor(max_workers=1) as pool,patch.object(self.controller,"authorized",observed):
            with self.controller.lock:
                pending=pool.submit(self.bookmark); self.assertTrue(waiting.wait(5)); self.controller.claim("replacement-controller",takeover=True)
            self.assertEqual(pending.result(timeout=5).status_code,423)
        self.assertEqual(self.path.read_bytes(),before)

    def test_concurrent_adds_and_duplicate_requests_do_not_lose_bookmarks(self):
        self.prepare(); store=self.app.state.store
        def add(index):return store.add_bookmark(self.project,self.source,{"id":f"parallel-bookmark-{index:016}","time":index})
        with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(add,list(range(12))*2))
        self.assertEqual(self.snapshot()["bookmark_count"],12)

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

    def test_foreign_origin_is_rejected_and_input_errors_are_json(self):
        self.assertEqual(self.client.post("/api/controller/claim", json={"page_id": self.page}, headers={"Origin": "https://other.example"}).status_code, 403)
        response = self.client.post("/api/controller/claim", json={"page_id": 123})
        self.assertEqual(response.status_code, 422)
        self.assertIn("error", response.json())
        self.assertEqual(self.client.get("/assets/not-an-asset").status_code, 404)

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


class SourceNameTests(unittest.TestCase):
    def test_numeric_episode_aliases(self):
        for alias in ["Episode 7", "Episode 07", "EP 7", "ep07", "Episode 007", " Episode   07 "]:
            self.assertEqual(source_key(alias), source_key("Episode 07"))

    def test_casefold_whitespace_and_display_spelling(self):
        self.assertEqual(source_key("  My   MOVIE "), source_key("my movie"))
        self.assertEqual(source_name("  Episode   07 "), "Episode   07")
        self.assertEqual(source_key("Straße"), source_key("STRASSE"))

    def test_custom_names_are_not_numeric_episodes(self):
        for name in ["OVA 1", "Season 2 - Episode 1", "Episode 1A", "Part 1", "Movie", "Season/Episode", "__proto__"]:
            self.assertNotEqual(source_key(name), source_key("Episode 01"))
        self.assertNotEqual(source_key("OVA 01"), source_key("OVA 1"))

    def test_suggestions_and_next_episode(self):
        self.assertEqual(next_episode([]), "Episode 01")
        self.assertEqual(next_episode(["EP7", "OVA 1", "Episode 02"]), "Episode 08")
        self.assertEqual(following_episode("Episode 02", ["Episode 02", "Episode 10"]), "Episode 03")
        self.assertEqual(following_episode("Movie", ["Movie", "Episode 10"]), "Episode 11")

    def test_names_are_bounded_and_serializable(self):
        for name in [None,"", "  ", "a"*101, "bad\nname", "bad\ud800"]:
            with self.assertRaises(AppError):source_name(name)
        self.assertEqual(source_name("日本語 \"Movie\""), "日本語 \"Movie\"")
