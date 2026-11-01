"""rCTF-backed platform client (challenge list, attachment download, flag submission).

The only network code in this project. It runs on the host, never inside the
analysis container: the sandbox stays offline, the host fetches inputs and
submits candidates. All parsing is defensive - descriptions and API payloads
are untrusted data.
"""

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ctf_forge.config import PlatformSettings
from ctf_forge.core.exceptions import ForgeError

MAX_ATTACHMENT_BYTES = 64 * 1024 * 1024
_LINK = re.compile(r"\[(?P<name>[^\]]{1,200})\]\((?P<url>https?://[^)\s]{1,2048})\)")
_SHA256 = re.compile(r"(?i)\bsha-?256\b[^0-9a-f]{0,20}(?P<hash>[0-9a-f]{64})\b")


@dataclass(frozen=True)
class Attachment:
    """One downloadable file referenced from a challenge description."""

    name: str
    url: str
    sha256: str | None


def safe_filename(raw: str) -> str:
    """Reduce a remote name to a single path component; never allow separators."""
    name = urllib.parse.unquote(raw).replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r"[\x00-\x1f<>:\"|?*]", "_", name).strip(" .")
    if not name or name in {".", ".."}:
        raise ForgeError("Attachment name is empty or unsafe")
    if len(name) > 120:
        stem = Path(name).name[:100]
        name = stem
    return name


def slug(name: str) -> str:
    """Stable directory name for a challenge."""
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-._").lower()
    if not value:
        raise ForgeError("Challenge name cannot be turned into a directory name")
    return value[:80]


def description_attachments(description: str) -> list[Attachment]:
    """Extract download links and their declared SHA-256 values from markdown text."""
    hashes = [m.group("hash").lower() for m in _SHA256.finditer(description)]
    found: list[Attachment] = []
    seen: set[str] = set()
    for match in _LINK.finditer(description):
        url = match.group("url")
        if url in seen:
            continue
        seen.add(url)
        name = safe_filename(url.rsplit("/", 1)[-1].split("?", 1)[0])
        found.append(Attachment(name=name, url=url, sha256=None))
    if len(hashes) == len(found) and found:
        found = [
            Attachment(name=item.name, url=item.url, sha256=digest)
            for item, digest in zip(found, hashes, strict=True)
        ]
    return found


class RctfClient:
    """Minimal rCTF v1/v2 client with cookie-free bearer authentication."""

    def __init__(
        self,
        settings: PlatformSettings,
        root: Path | None = None,
        transport: Callable[[str, str, dict[str, Any] | None], tuple[int, Any]] | None = None,
    ) -> None:
        self.settings = settings
        self.root = root
        self._transport = transport
        self._base_url = str(settings.base_url).rstrip("/") if settings.base_url else ""
        self.token = self._resolve_token()

    # ------------------------------------------------------------------ auth
    def _resolve_token(self) -> str:
        if self.settings.auth_token:
            return self.settings.auth_token.get_secret_value()
        path = self.settings.session_file
        if path is None and self.root is not None:
            path = self.root / ".data/hi-session.secret.json"
        if path is not None and Path(path).is_file():
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            token = data.get("auth_token")
            if isinstance(token, str) and token:
                if not self._base_url and data.get("base_url"):
                    self._base_url = str(data["base_url"]).rstrip("/")
                return token
        raise ForgeError(
            "No platform token: set CTF_FORGE_PLATFORM__AUTH_TOKEN or provide a session file"
        )

    @property
    def base_url(self) -> str:
        if not self._base_url:
            raise ForgeError("Platform base_url is not configured")
        return self._base_url

    def _default_transport(
        self, method: str, url: str, body: dict[str, Any] | None
    ) -> tuple[int, Any]:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", "Bearer " + self.token)
        request.add_header("User-Agent", self.settings.user_agent)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            raw, status = exc.read(), exc.code
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ForgeError(f"Platform request failed ({type(exc).__name__})") from None
        try:
            return status, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            raise ForgeError("Platform returned a non-JSON response") from None

    def _call_raw(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        url = self.base_url + path
        transport = self._transport or self._default_transport
        status, payload = transport(method, url, body)
        if status == 403 and isinstance(payload, dict) and "cloudflare" in str(payload).lower():
            raise ForgeError(
                "Platform WAF rejected the request; a browser user_agent is required "
                "(see configs/platform.yaml)"
            )
        if not isinstance(payload, dict):
            raise ForgeError("Unexpected platform response shape")
        kind = str(payload.get("kind", ""))
        if status >= 400 or kind.startswith("bad"):
            message = str(payload.get("message", kind or f"HTTP {status}"))[:300]
            raise ForgeError(f"Platform rejected the request: {message}")
        if "data" not in payload:
            raise ForgeError("Platform response has no data field")
        return payload

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._call_raw(method, path, body)["data"]

    # ------------------------------------------------------------- endpoints
    def me(self) -> dict[str, Any]:
        data = self._call("GET", "/api/v2/users/me")
        if not isinstance(data, dict):
            raise ForgeError("Unexpected /users/me payload")
        return data

    def challenges(self) -> list[dict[str, Any]]:
        data = self._call("GET", "/api/v2/challs")
        if not isinstance(data, list):
            raise ForgeError("Unexpected challenge list payload")
        return [item for item in data if isinstance(item, dict) and item.get("id")]

    def find(self, name_or_id: str) -> dict[str, Any]:
        wanted = name_or_id.strip().lower()
        for item in self.challenges():
            if str(item.get("id")) == name_or_id or str(item.get("name", "")).lower() == wanted:
                return item
        raise ForgeError(f"Challenge not found on platform: {name_or_id}")

    def submit(self, challenge_id: str, flag: str) -> dict[str, Any]:
        """Submit one candidate; a wrong flag is a verdict, not an exception.

        Only transport-level failures (network, WAF, 5xx) raise, so a rejected
        candidate cannot abort an otherwise healthy solving session.
        """
        if not flag.strip() or len(flag) > 1024:
            raise ForgeError("Candidate flag must be non-empty and at most 1024 characters")
        transport = self._transport or self._default_transport
        status, payload = transport(
            "POST", self.base_url + f"/api/v1/challs/{challenge_id}/submit", {"flag": flag}
        )
        if not isinstance(payload, dict):
            raise ForgeError("Unexpected platform response shape")
        if status == 403 and "cloudflare" in str(payload).lower():
            raise ForgeError(
                "Platform WAF rejected the submission; a browser user_agent is required"
            )
        kind = str(payload.get("kind", ""))
        if status >= 500 or not kind:
            raise ForgeError(f"Platform submission failed (HTTP {status})")
        data = payload.get("data")
        return {
            "kind": kind,
            "message": str(payload.get("message", ""))[:300],
            "accepted": not kind.startswith("bad"),
            "data": data if isinstance(data, dict) else {},
        }

    # -------------------------------------------------------------- download
    def download(self, attachment: Attachment, destination: Path) -> dict[str, Any]:
        request = urllib.request.Request(attachment.url, method="GET")
        request.add_header("User-Agent", self.settings.user_agent)
        try:
            with urllib.request.urlopen(request, timeout=self.settings.timeout_seconds) as response:
                size = response.headers.get("Content-Length")
                if size and int(size) > MAX_ATTACHMENT_BYTES:
                    raise ForgeError(f"Attachment exceeds {MAX_ATTACHMENT_BYTES} bytes")
                chunks: list[bytes] = []
                total = 0
                while chunk := response.read(65536):
                    total += len(chunk)
                    if total > MAX_ATTACHMENT_BYTES:
                        raise ForgeError(f"Attachment exceeds {MAX_ATTACHMENT_BYTES} bytes")
                    chunks.append(chunk)
        except urllib.error.HTTPError as exc:
            raise ForgeError(f"Attachment download failed (HTTP {exc.code})") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ForgeError(f"Attachment download failed ({type(exc).__name__})") from None
        blob = b"".join(chunks)
        digest = hashlib.sha256(blob).hexdigest()
        verified = attachment.sha256 is None or digest == attachment.sha256
        target = destination / attachment.name
        target.write_bytes(blob)
        return {
            "name": attachment.name,
            "path": str(target),
            "bytes": len(blob),
            "sha256": digest,
            "expected_sha256": attachment.sha256,
            "verified": verified,
        }

    def pull(self, name_or_id: str, destination: Path) -> dict[str, Any]:
        """Download every attachment referenced by a challenge into destination."""
        challenge = self.find(name_or_id)
        description = str(challenge.get("description") or "")
        attachments = description_attachments(description)
        if not attachments:
            raise ForgeError(
                "Challenge description lists no downloadable attachment; "
                "this workflow only supports file-based challenges"
            )
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "description.md").write_text(description, encoding="utf-8")
        files = [self.download(item, destination) for item in attachments]
        manifest = {
            "challenge_id": challenge["id"],
            "name": challenge.get("name"),
            "category": challenge.get("category"),
            "points": challenge.get("points"),
            "solves": challenge.get("solves"),
            "author": challenge.get("author"),
            "directory": str(destination),
            "files": files,
        }
        (destination / "challenge.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8"
        )
        manifest["all_verified"] = all(item["verified"] for item in files)
        return manifest
