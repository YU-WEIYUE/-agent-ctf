"""Platform adapter tests: parsing, fail-closed submission, and host-only downloads."""

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ctf_forge.config import PlatformSettings, Settings
from ctf_forge.core.exceptions import ForgeError
from ctf_forge.platform.rctf import (
    Attachment,
    RctfClient,
    description_attachments,
    safe_filename,
    slug,
)
from ctf_forge.tools.registry import candidate_values
from ctf_forge.workflow.session import Session

DESCRIPTION = """Evidence tag IR-2231-A.

It expects one argument: `./cold-beacon <key>`.

**Files:** [cold-beacon.zip](https://example.invalid/cold-beacon/a5e6/cold-beacon.zip)

SHA-256: `a01791f8259c7bcf1eb07f578abc686b2a4ab78d4fe410f565c74624e52610d8`

**Flag Format:** `hiCTF{}`
"""


def make_client(handler: Any) -> RctfClient:
    return RctfClient(
        PlatformSettings(base_url="https://ctf.example", auth_token="test-token"),  # type: ignore[arg-type]
        transport=handler,
    )


def test_description_parses_link_and_hash() -> None:
    attachments = description_attachments(DESCRIPTION)
    assert len(attachments) == 1
    assert attachments[0].name == "cold-beacon.zip"
    digest = "a01791f8259c7bcf1eb07f578abc686b2a4ab78d4fe410f565c74624e52610d8"
    assert attachments[0].sha256 == digest


def test_description_without_links_is_empty() -> None:
    assert description_attachments("No files here, only a hiCTF{not-a-file} format note.") == []


def test_description_two_links_pair_with_two_hashes() -> None:
    text = (
        "[a.zip](https://example.invalid/x/a.zip)\n"
        "[b.bin](https://example.invalid/x/b.bin)\n"
        "SHA-256: `" + "1" * 64 + "`\nSHA-256: `" + "2" * 64 + "`\n"
    )
    attachments = description_attachments(text)
    assert [item.name for item in attachments] == ["a.zip", "b.bin"]
    assert [item.sha256 for item in attachments] == ["1" * 64, "2" * 64]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://x/y/cold-beacon.zip", "cold-beacon.zip"),
        ("../../etc/passwd", "passwd"),
        ("..\\..\\windows\\evil.bin", "evil.bin"),
        ("%2e%2e%2fescape.zip", "escape.zip"),
    ],
)
def test_safe_filename_strips_path_components(raw: str, expected: str) -> None:
    assert safe_filename(raw) == expected


def test_safe_filename_rejects_empty() -> None:
    with pytest.raises(ForgeError):
        safe_filename("   ")


def test_slug_is_directory_safe() -> None:
    assert slug("Cold Beacon") == "cold-beacon"
    assert slug("The Inner Engine!") == "the-inner-engine"
    with pytest.raises(ForgeError):
        slug("///")


def test_challenge_list_and_lookup() -> None:
    def handler(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        assert url.endswith("/api/v2/challs")
        return 200, {
            "kind": "goodChallengesV2",
            "data": [
                {"id": "abc-123-xyz", "name": "Cold Beacon", "category": "Reverse"},
                {"id": "def-456", "name": "Signal Lock", "category": "Reverse"},
            ],
        }

    client = make_client(handler)
    assert [item["name"] for item in client.challenges()] == ["Cold Beacon", "Signal Lock"]
    assert client.find("cold beacon")["id"] == "abc-123-xyz"
    assert client.find("def-456")["name"] == "Signal Lock"
    with pytest.raises(ForgeError, match="not found"):
        client.find("Missing")


def test_bad_flag_is_a_rejection_verdict_not_success() -> None:
    def handler(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        assert method == "POST" and url.endswith("/api/v1/challs/abc-123-xyz/submit")
        assert body == {"flag": "hiCTF{nope}"}
        return 400, {"kind": "badFlag", "message": "The flag was incorrect."}

    verdict = make_client(handler).submit("abc-123-xyz", "hiCTF{nope}")
    assert verdict["accepted"] is False
    assert verdict["kind"] == "badFlag"
    assert verdict["message"] == "The flag was incorrect."


def test_good_flag_submission_returns_verdict() -> None:
    def handler(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        return 200, {"kind": "goodFlag", "message": "Solved.", "data": {"score": 54}}

    verdict = make_client(handler).submit("abc-123-xyz", "hiCTF{ok}")
    assert verdict["kind"] == "goodFlag"
    assert verdict["data"] == {"score": 54}


def test_cloudflare_block_is_explained() -> None:
    def handler(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        return 403, {"title": "Error 1010", "cloudflare_error": "True"}

    with pytest.raises(ForgeError, match="user_agent"):
        make_client(handler).me()


def test_pull_verifies_hash_and_writes_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"PK\x03\x04fake-zip"
    digest = hashlib.sha256(blob).hexdigest()

    def handler(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        if url.endswith("/api/v2/challs"):
            return 200, {
                "kind": "goodChallengesV2",
                "data": [{"id": "abc-123-xyz", "name": "Cold Beacon", "category": "Reverse"}],
            }
        return 200, {"kind": "goodChallengeV2", "data": {"id": "abc-123-xyz", "files": []}}

    client = make_client(handler)

    class Payload:
        headers: dict[str, str] = {}
        status = 200

        def __init__(self) -> None:
            self._sent = False

        def read(self, _size: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return blob

        def __enter__(self) -> "Payload":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Payload())
    monkeypatch.setattr(
        "ctf_forge.platform.rctf.description_attachments",
        lambda text: [Attachment(name="cold-beacon.zip", url="https://x/y", sha256=digest)],
    )
    manifest = client.pull("abc-123-xyz", tmp_path / "dest")
    assert manifest["all_verified"] is True
    assert (tmp_path / "dest/cold-beacon.zip").read_bytes() == blob
    manifest = json.loads((tmp_path / "dest/challenge.json").read_text())
    assert manifest["challenge_id"] == "abc-123-xyz"


def test_pull_rejects_hash_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(method: str, url: str, body: dict[str, Any] | None) -> tuple[int, Any]:
        return 200, {
            "kind": "goodChallengesV2",
            "data": [{"id": "abc-123-xyz", "name": "Cold Beacon", "category": "Reverse"}],
        }

    class Payload:
        headers: dict[str, str] = {}

        def __init__(self) -> None:
            self._sent = False

        def read(self, _size: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return b"tampered"

        def __enter__(self) -> "Payload":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Payload())
    monkeypatch.setattr(
        "ctf_forge.platform.rctf.description_attachments",
        lambda text: [Attachment(name="cold-beacon.zip", url="https://x/y", sha256="0" * 64)],
    )
    manifest = make_client(handler).pull("abc-123-xyz", tmp_path / "dest")
    assert manifest["all_verified"] is False


def test_platform_accepted_flag_is_the_only_success_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "fixture"
    binary.write_bytes(b"\x7fELF fixture")
    session = Session.create(tmp_path, Settings(), binary, "Test", None, "abc-123-xyz")
    session.record.status = "running"

    class Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def submit(self, challenge_id: str, flag: str) -> dict[str, Any]:
            assert challenge_id == "abc-123-xyz"
            return {"kind": "goodFlag", "message": "Solved.", "accepted": True, "data": {}}

    monkeypatch.setattr("ctf_forge.platform.rctf.RctfClient", Client)
    result = session.apply("submit_flag", {"value": "hiCTF{accepted}"})
    assert result["complete"] is True
    assert session.record.candidate_flags[-1].status == "platform_accepted"
    evidence = session.record.candidate_flags[-1].verification_evidence
    assert evidence == "platform_submission:goodFlag"
    assert session.record.verified_flag == "hiCTF{accepted}"


def test_platform_rejection_does_not_mark_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary = tmp_path / "fixture"
    binary.write_bytes(b"\x7fELF fixture")
    session = Session.create(tmp_path, Settings(), binary, "Test", None, "abc-123-xyz")
    session.record.status = "running"

    class Client:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def submit(self, challenge_id: str, flag: str) -> dict[str, Any]:
            return {
                "kind": "badFlag",
                "message": "The flag was incorrect.",
                "accepted": False,
                "data": {},
            }

    monkeypatch.setattr("ctf_forge.platform.rctf.RctfClient", Client)
    result = session.apply("submit_flag", {"value": "hiCTF{wrong}"})
    assert result["valid"] is False
    assert session.record.status != "succeeded"
    assert session.record.candidate_flags[-1].status == "rejected"
    assert session.record.verified_flag is None


def test_candidate_regex_keeps_hiCTF_prefix() -> None:
    assert candidate_values("the key is hiCTF{abc_123} ok") == ["hiCTF{abc_123}"]
    assert candidate_values("flag{plain} and picoCTF{x}") == ["flag{plain}", "picoCTF{x}"]
    assert candidate_values("SOMETHINGCTF{clipped}") == []
