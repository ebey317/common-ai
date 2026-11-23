"""
Google Drive adapter — real connector.

STATE (2026-11-23): the stub is gone. scan() lists real Drive metadata through
Drive v3, apply() moves files between folders, undo() moves them back. No delete
is wired anywhere, by design.

AUTH: this adapter does NOT run its own OAuth flow. Hermes already holds a
working, auto-refreshing token at ~/.hermes/google_token.json with the `drive`
scope — a second consent screen would be a second thing to re-authorise every
seven days while the app sits in Testing mode. It reads that token first and
falls back to sensei-clean's own ~/.config/sensei-clean/gdrive.token only if
Hermes' is absent.

  scanners see metadata only: id, name, mimeType, size, modifiedTime,
  md5Checksum, parents, trashed. No file content is ever downloaded.

apply() performs cloud_move only:
    files.update(addParents=<destination>, removeParents=<source>)
and returns an UndoRecord carrying the reverse move, so undo() is exact.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

from ..schemas import (
    AccessGrant,
    ActionRecord,
    ApplyResult,
    CapabilityReport,
    ItemRecord,
    UndoRecord,
)
from .cloud_drive import CONFIG_DIR, CloudDriveAdapter


CLIENT_SECRET_FILE = CONFIG_DIR / "gdrive_client.json"
HERMES_TOKEN_FILE = Path.home() / ".hermes" / "google_token.json"
FOLDER_MIME = "application/vnd.google-apps.folder"

LIST_FIELDS = (
    "nextPageToken, files("
    "id,name,mimeType,size,modifiedTime,createdTime,md5Checksum,parents,"
    "trashed,webViewLink)"
)


def _deps_present() -> bool:
    try:
        import google.oauth2.credentials  # noqa: F401
        import googleapiclient.discovery  # noqa: F401
        return True
    except Exception:
        return False


def _token_candidates() -> List[Path]:
    return [HERMES_TOKEN_FILE, CONFIG_DIR / "gdrive.token"]


def _credentials():
    """Build Credentials from the first token file that exists."""
    from google.oauth2.credentials import Credentials

    for path in _token_candidates():
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        return Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri=data.get("token_uri") or "https://oauth2.googleapis.com/token",
            client_id=data.get("client_id"),
            client_secret=data.get("client_secret"),
            scopes=data.get("scopes"),
        ), path
    return None, None


def _service():
    creds, _ = _credentials()
    if creds is None:
        return None
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=creds, cache_discovery=False)


class GoogleDriveAdapter(CloudDriveAdapter):
    name = "gdrive"
    provider_id = "gdrive"
    provider_label = "Google Drive"

    # ── capability ───────────────────────────────────────────────

    @classmethod
    def is_configured(cls) -> bool:
        if not _deps_present():
            return False
        return any(p.is_file() for p in _token_candidates())

    def _account_label(self) -> str:  # type: ignore[override]
        return "hermes-oauth" if HERMES_TOKEN_FILE.is_file() else "sensei-oauth"

    def probe(self) -> CapabilityReport:
        blockers: list[str] = []
        if not _deps_present():
            blockers.append(
                "gdrive-missing-deps: pip install google-api-python-client google-auth"
            )
        if not any(p.is_file() for p in _token_candidates()):
            blockers.append(
                "gdrive-not-authorized: no token at %s or %s"
                % (HERMES_TOKEN_FILE, CONFIG_DIR / "gdrive.token")
            )
        return CapabilityReport(
            adapter=self.name,
            provider=self.provider_id,
            capability="api",
            account_label=self._account_label() or "(not connected)",
            root=self.root,
            available=not blockers,
            supported_actions=["cloud_move"],
            blockers=blockers,
            notes=[
                "Live Drive v3 connector using the Hermes Google token.",
                "Metadata only — no file content is read or downloaded.",
                "No delete actions in v1 — move/organise only.",
            ],
        )

    def authorize(self, mode: str) -> AccessGrant:
        """No separate consent flow: reuse the token Hermes already maintains."""
        tok = next((p for p in _token_candidates() if p.is_file()), None)
        if tok is None:
            return AccessGrant(mode=mode, granted=False, details={
                "blocker": "no-token",
                "hint": "authorise Google via the google-workspace skill once; "
                        "this adapter reuses that token",
            })
        return AccessGrant(mode=mode, granted=True, details={
            "provider": "gdrive",
            "token_file": str(tok),
            "note": "reusing existing OAuth token; refresh handled by the token owner",
        })

    # ── scan ─────────────────────────────────────────────────────

    def _root_folder_id(self) -> str:
        """self.root looks like 'gdrive:<folder_id>' or 'gdrive:root'."""
        _, _, fid = self.root.partition(":")
        return fid or "root"

    def scan(self, cursor: Optional[str] = None) -> Iterator[ItemRecord]:
        svc = _service()
        if svc is None:
            return

        folder_id = cursor or self._root_folder_id()
        page_token: Optional[str] = None
        while True:
            try:
                resp = svc.files().list(
                    q="'%s' in parents and trashed = false" % folder_id,
                    fields=LIST_FIELDS,
                    pageToken=page_token,
                    pageSize=200,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
            except Exception as exc:  # noqa: BLE001 — surface, do not crash the run
                raise RuntimeError(
                    "gdrive scan failed for folder %s: %s" % (folder_id, exc)
                ) from exc

            for f in resp.get("files", []):
                yield self._to_item(f, folder_id)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

    def _to_item(self, f: dict, parent_id: str) -> ItemRecord:
        is_folder = f.get("mimeType") == FOLDER_MIME
        size = int(f.get("size") or 0)
        md5 = f.get("md5Checksum")
        name = f.get("name") or "(unnamed)"
        return ItemRecord(
            schema_version="sensei.item.v1",
            run_id=self.run_id,
            item_id="gdrive:%s" % f.get("id"),
            source={
                "adapter": self.name,
                "provider": self.provider_id,
                "capability": "api",
                "account_label": self._account_label(),
                "root": self.root,
            },
            identity={
                "path": "gdrive:%s" % f.get("id"),
                "provider_id": f.get("id"),
                "parent_id": parent_id,
                "relative_path": name,
                "web_view_link": f.get("webViewLink"),
            },
            kind="folder" if is_folder else "file",
            display_name=name,
            mime=f.get("mimeType") or "",
            size_bytes=size,
            timestamps={
                "created": f.get("createdTime"),
                "modified": f.get("modifiedTime"),
                "taken": None,
            },
            hashes={
                "sha256": None,
                "md5": md5,
                "provider_hash": md5,
                "perceptual_hash": None,
            },
            features={
                "extension": "",
                "dimensions": None,
                "duration_seconds": None,
                "text_snippet": None,
                "face_count": None,
                "screenshot_likely": False,
            },
            sensitivity="normal",
            category_guess="",
            confidence=0.9 if md5 else 0.6,
            risk=10,
            reversible_actions=["cloud_move"],
            required_access=["read_metadata"],
            dependencies=[],
            notes=[],
        )

    # ── move / undo ──────────────────────────────────────────────

    def enrich(self, item: ItemRecord, jobs: List[str]) -> ItemRecord:
        return item

    @staticmethod
    def _split(path: str) -> Tuple[str, str]:
        """'gdrive:<id>' -> ('gdrive', '<id>')."""
        prov, _, fid = (path or "").partition(":")
        return prov, fid

    def apply(self, action: ActionRecord) -> ApplyResult:
        if action.action_type != "cloud_move":
            return ApplyResult(
                action_id=action.action_id,
                success=False,
                message="gdrive supports cloud_move only, not %r" % action.action_type,
            )

        svc = _service()
        if svc is None:
            return ApplyResult(
                action_id=action.action_id,
                success=False,
                message="gdrive not configured: no usable Google token",
            )

        _, file_id = self._split(action.item_id)
        _, src = self._split(action.source_path)
        _, dst = self._split(action.destination_path or "")
        if not file_id or not dst:
            return ApplyResult(
                action_id=action.action_id,
                success=False,
                message="cloud_move needs a file id and a destination folder id",
            )

        try:
            svc.files().update(
                fileId=file_id,
                addParents=dst,
                removeParents=src or None,
                fields="id,parents",
                supportsAllDrives=True,
            ).execute()
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(
                action_id=action.action_id,
                success=False,
                message="gdrive move failed: %s" % exc,
            )

        undo = UndoRecord(
            schema_version="sensei.undo.v1",
            run_id=action.run_id,
            undo_id="undo-%s" % action.action_id,
            adapter=self.name,
            action_id=action.action_id,
            source_path=action.destination_path or "",
            destination_path=action.source_path,
            metadata={"file_id": file_id, "moved_to": dst, "moved_from": src},
        )
        return ApplyResult(
            action_id=action.action_id,
            success=True,
            message="moved %s into %s" % (file_id, dst),
            undo_record=undo,
        )

    def undo(self, undo_record: UndoRecord) -> ApplyResult:
        svc = _service()
        if svc is None:
            return ApplyResult(
                action_id=undo_record.action_id,
                success=False,
                message="gdrive not configured: nothing to undo",
            )

        file_id = undo_record.metadata.get("file_id") or self._split(
            undo_record.source_path)[1]
        back_to = self._split(undo_record.destination_path)[1]
        away_from = undo_record.metadata.get("moved_to") or self._split(
            undo_record.source_path)[1]
        if not file_id or not back_to:
            return ApplyResult(
                action_id=undo_record.action_id,
                success=False,
                message="undo record incomplete",
            )

        try:
            svc.files().update(
                fileId=file_id,
                addParents=back_to,
                removeParents=away_from or None,
                fields="id,parents",
                supportsAllDrives=True,
            ).execute()
        except Exception as exc:  # noqa: BLE001
            return ApplyResult(
                action_id=undo_record.action_id,
                success=False,
                message="gdrive undo failed: %s" % exc,
            )

        return ApplyResult(
            action_id=undo_record.action_id,
            success=True,
            message="moved %s back to %s" % (file_id, back_to),
        )

    def open_view(self, item: ItemRecord) -> str:
        link = item.identity.get("web_view_link")
        if link:
            return link
        fid = item.identity.get("provider_id", "")
        return "https://drive.google.com/file/d/%s/view" % fid if fid else ""
