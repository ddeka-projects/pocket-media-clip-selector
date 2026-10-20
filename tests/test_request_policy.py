"""Exercise LAN policy, configuration, and server lifecycle through real ASGI requests."""

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from pocket_media_clip_selector.app import create_app
from pocket_media_clip_selector.config import REPOSITORY, Settings, load_settings
from pocket_media_clip_selector.errors import AppError
from pocket_media_clip_selector.process_lock import ProcessLock


class RequestPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "Media Projects"
        self.root.mkdir()
        self.app = create_app(Settings(self.root), lock_library=False)
        self.client = self.make_client()
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def make_client(self, peer="127.0.0.1", *, base_url="http://127.0.0.1"):
        return TestClient(self.app, base_url=base_url, client=(peer, 50000))

    def assert_error(self, response, status, code):
        self.assertEqual(status, response.status_code, response.text)
        body = response.json()
        self.assertFalse(body["ok"])
        self.assertEqual(code, body["error"]["code"])
        self.assertTrue(body["error"]["message"])

    def claim(self, page="page-one"):
        response = self.client.post("/api/controller/claim", json={"page_id": page})
        self.assertEqual(200, response.status_code, response.text)
        return {"X-Page-Id": page, "X-Controller-Token": response.json()["token"]}

    def test_static_and_health_are_public_but_data_requires_explicit_control(self):
        self.assertEqual(200, self.client.get("/").status_code)
        self.assertEqual(200, self.client.get("/static/app.js").status_code)
        health = self.client.get("/health")
        self.assertEqual(200, health.status_code)
        self.assertEqual("pocket_media_clip_selector", health.json()["app"])
        self.assert_error(self.client.get("/api/projects"), 409, "controller_required")
        headers = self.claim()
        self.assertEqual(200, self.client.get("/api/projects", headers=headers).status_code)
        self.assert_error(self.client.get("/api/projects"), 423, "controller_transferred")
        next_page = self.client.post("/api/controller/takeover", json={"page_id": "page-two"})
        self.assertEqual(200, next_page.status_code)
        self.assert_error(
            self.client.post("/api/projects", json={"name": "Rejected old write"}, headers=headers),
            423,
            "controller_transferred",
        )
        self.assertFalse((self.root / "Rejected old write").exists())

    def test_host_header_rejects_public_foreign_and_malformed_authorities(self):
        invalid = (
            "attacker.example",
            "8.8.8.8",
            "0.0.0.0",
            "[::]",
            "localhost:0",
            "localhost:65536",
            "localhost:not-a-port",
            "user@localhost",
            "user:secret@localhost",
            "localhost/path",
            "localhost?query=yes",
            "localhost#fragment",
            "[broken",
        )
        for host in invalid:
            with self.subTest(host=host):
                self.assert_error(
                    self.client.get("/health", headers={"Host": host}), 403, "forbidden_request"
                )
        self.assert_error(
            self.client.get("/health", headers={"Host": ""}), 403, "forbidden_request"
        )

    def test_private_loopback_and_configured_local_hostname_hosts_are_allowed(self):
        for host in (
            "localhost",
            "127.0.0.1",
            "192.168.10.20:8767",
            "10.0.0.4",
            "[::1]",
            "[fe80::1]",
        ):
            with self.subTest(host=host):
                self.assertEqual(
                    200, self.client.get("/health", headers={"Host": host}).status_code
                )
        app = create_app(Settings(self.root, host="my-home-pc"), lock_library=False)
        with TestClient(app, base_url="http://my-home-pc", client=("127.0.0.1", 50000)) as client:
            self.assertEqual(200, client.get("/health").status_code)

    def test_private_and_loopback_peers_are_allowed_but_public_or_invalid_peers_are_blocked(self):
        for peer in ("127.0.0.1", "::1", "192.168.0.50", "10.0.0.50", "169.254.1.1", "fe80::1"):
            with self.subTest(peer=peer):
                client = self.make_client(peer)
                self.assertEqual(200, client.get("/health").status_code)
                client.close()
        for peer in ("8.8.8.8", "1.1.1.1", "2001:4860:4860::8888", "not-an-address"):
            with self.subTest(peer=peer):
                client = self.make_client(peer)
                self.assert_error(client.get("/health"), 403, "forbidden_request")
                client.close()

    def test_foreign_origin_read_claim_and_write_are_rejected_without_effect(self):
        owner = self.claim()
        for origin in (
            "https://attacker.example",
            "http://localhost",
            "null",
            "http://127.0.0.1:8767",
        ):
            with self.subTest(origin=origin):
                self.assert_error(
                    self.client.get("/api/projects", headers=owner | {"Origin": origin}),
                    403,
                    "foreign_origin",
                )
                self.assert_error(
                    self.client.post(
                        "/api/controller/takeover",
                        json={"page_id": "foreign-page"},
                        headers={"Origin": origin},
                    ),
                    403,
                    "foreign_origin",
                )
                self.assert_error(
                    self.client.post(
                        "/api/projects",
                        json={"name": "Foreign write"},
                        headers=owner | {"Origin": origin},
                    ),
                    403,
                    "foreign_origin",
                )
        self.assertFalse((self.root / "Foreign write").exists())
        self.assertEqual(
            200,
            self.client.get(
                "/api/projects", headers=owner | {"Origin": "http://127.0.0.1"}
            ).status_code,
        )

    def test_cross_site_fetch_without_origin_cannot_claim_or_mutate(self):
        self.assert_error(
            self.client.post(
                "/api/controller/claim",
                json={"page_id": "foreign-page"},
                headers={"Sec-Fetch-Site": "cross-site"},
            ),
            403,
            "foreign_origin",
        )
        owner = self.claim()
        self.assert_error(
            self.client.post(
                "/api/projects",
                json={"name": "Cross-site write"},
                headers=owner | {"Sec-Fetch-Site": "cross-site"},
            ),
            403,
            "foreign_origin",
        )
        self.assertFalse((self.root / "Cross-site write").exists())
        self.assertEqual(
            201,
            self.client.post(
                "/api/projects",
                json={"name": "Local write"},
                headers=owner | {"Sec-Fetch-Site": "same-origin"},
            ).status_code,
        )

    def test_successful_responses_have_baseline_browser_protection_headers(self):
        for path in ("/", "/static/app.js", "/health"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual("nosniff", response.headers["X-Content-Type-Options"])
                self.assertEqual("no-store", response.headers["Cache-Control"])
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])


class ConfigurationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.library = self.root / "Media $literal with spaces"
        self.library.mkdir()
        self.env = self.root / ".env"

    def test_full_prefix_and_literal_quoted_directory_with_environment_override(self):
        self.env.write_text(
            f'\ufeffPOCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY="{self.library}"\n'
            "POCKET_MEDIA_CLIP_SELECTOR_HOST=0.0.0.0\n"
            "POCKET_MEDIA_CLIP_SELECTOR_PORT=8767\n",
            encoding="utf-8",
        )
        settings = load_settings(self.env, environ={"POCKET_MEDIA_CLIP_SELECTOR_PORT": "9876"})
        self.assertEqual(self.library, settings.working_directory)
        self.assertEqual(9876, settings.port)
        self.assertEqual("0.0.0.0", settings.host)

    def test_obsolete_or_unprefixed_names_do_not_silently_choose_a_library(self):
        for key in ("WORKING_DIRECTORY", "POCKET_CLIP_SELECTOR_WORKING_DIRECTORY"):
            with self.subTest(key=key):
                self.env.write_text(f"{key}={self.library}\n", encoding="utf-8")
                with self.assertRaisesRegex(
                    ValueError, "POCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY"
                ):
                    load_settings(self.env, environ={})

    def test_relative_missing_repository_and_ancestor_libraries_are_rejected(self):
        for directory in (
            "relative/media",
            str(self.root / "missing"),
            str(REPOSITORY),
            str(REPOSITORY.parent),
        ):
            with self.subTest(directory=directory):
                with self.assertRaises(ValueError):
                    load_settings(
                        self.env,
                        environ={"POCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY": directory},
                    )

    def test_library_symlink_is_rejected_before_startup(self):
        link = self.root / "Linked library"
        try:
            link.symlink_to(self.library, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Directory links are unavailable: {error}")
        with self.assertRaises(AppError) as error:
            load_settings(
                self.env, environ={"POCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY": str(link)}
            )
        self.assertEqual("unsafe_path", error.exception.code)

    def test_invalid_port_and_host_report_their_current_setting_name(self):
        for suffix, value in (
            ("PORT", "bad"),
            ("PORT", "0"),
            ("PORT", "65536"),
            ("HOST", ""),
            ("HOST", "two names"),
        ):
            with self.subTest(suffix=suffix, value=value):
                key = "POCKET_MEDIA_CLIP_SELECTOR_" + suffix
                with self.assertRaisesRegex(ValueError, key):
                    load_settings(
                        self.env,
                        environ={
                            "POCKET_MEDIA_CLIP_SELECTOR_WORKING_DIRECTORY": str(self.library),
                            key: value,
                        },
                    )


class ServerLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.settings = Settings(self.root)

    def client(self, app):
        return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

    def test_real_lifespan_rejects_duplicate_server_and_releases_on_exit(self):
        first = create_app(self.settings)
        with self.client(first) as client:
            token = client.post("/api/controller/claim", json={"page_id": "active-page"}).json()[
                "token"
            ]
            with self.assertRaisesRegex(RuntimeError, "Another server"):
                with self.client(create_app(self.settings)):
                    self.fail("A duplicate server unexpectedly started")
            self.assertEqual(
                200,
                client.get(
                    "/api/projects",
                    headers={"X-Page-Id": "active-page", "X-Controller-Token": token},
                ).status_code,
            )
        with self.client(create_app(self.settings)) as restarted:
            self.assertEqual(200, restarted.get("/health").status_code)
            self.assertEqual(409, restarted.get("/api/projects").status_code)
        self.assertEqual({"claimed": False}, first.state.controller.snapshot())

    def test_invalid_library_startup_does_not_leave_a_process_guard(self):
        missing = self.root / "missing"
        with self.assertRaises(OSError):
            create_app(Settings(missing))
        missing.mkdir()
        with ProcessLock(missing):
            pass
        with self.client(create_app(Settings(missing))) as client:
            self.assertEqual(200, client.get("/health").status_code)


if __name__ == "__main__":
    unittest.main()
