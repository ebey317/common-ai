#!/usr/bin/env python3
"""
COMMON AI - vault
=================
Personal files need somewhere to live that is not one machine.

Every other module in this repo reads profile.json, ledger.csv and friends from
the working directory. That is fine until the machine dies, or the person moves
to a laptop, and the whole record - the applications, the standards, the
employment history - is gone. The vault puts those files in the owner's OWN
cloud storage and can pull them back onto a clean install.

  python3 vault.py providers         # which backends are configured here
  python3 vault.py status            # local vs cloud, and which side is newer
  python3 vault.py backup            # push files the cloud does not have newer
  python3 vault.py restore           # pull files this machine does not have newer
  python3 vault.py backup --force    # push regardless of what the cloud thinks

TWO PROVIDERS, ONE SHAPE
------------------------
`google`   Google Drive v3, using the OAuth token already on this machine.
`onedrive` Microsoft Graph, using a token file of the same shape.

Neither is required to exist. An unconfigured provider reports NOT CONFIGURED
and the vault uses whichever one is; a person who lives in OneDrive and has
never touched Google gets a working vault and vice versa. That is the point of
splitting the backend from the commands.

THE CONFLICT RULE
-----------------
**Local is the source of truth; the cloud is a backup, never a second owner.**
Two copies of one fact is exactly how a record starts disagreeing with itself.
So nothing is ever overwritten silently:

  backup    pushes only files the cloud does not already hold somewhere newer
  restore   pulls only files this machine does not already hold somewhere newer

Anything newer on the far side is reported and left alone until you pass
--force or --take-cloud. A backup that quietly eats a newer local file is worse
than no backup at all.

WHAT DOES NOT GO UP
-------------------
assets/ - the wardrobe photographs - is excluded unless you pass --with-assets.
Those are deliberately local-only: a person's body photos do not need to be in
a cloud account to make a resume better. Everything else here is text the owner
typed about their own life, and it belongs to them.

Zero dependencies. Plain HTTPS over the standard library, so this works on any
machine with Python 3.8+ and no pip step.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "vault.json")

DEFAULT_FOLDER = "Common AI/vault"
DEFAULT_PROVIDER = "auto"

# The private files. Anything not on this list is not uploaded by name, so a
# new personal file has to be added deliberately rather than leaking upward.
FILES = [
    "profile.json",
    "ledger.csv",
    "prefill.json",
    "inventory.json",
    "layer_state.json",
    "opportunities.json",
    ".pulse_state.json",
]

# Local-only by default. Not an oversight - see "WHAT DOES NOT GO UP" above.
WITHHELD = ["assets"]

# Cloud mtimes are rounded and clock skew is real, so a difference of a couple
# of seconds is not "newer", it is noise. Without this, every status run would
# claim the far side had changed.
TOLERANCE = 2.0

TIMEOUT = 60


class VaultError(Exception):
    pass


# --------------------------------------------------------------- small helpers
def _iso(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s):
    if not s:
        return 0.0
    try:
        return datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(
            tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


def _req(url, method="GET", body=None, headers=None):
    """One HTTPS call. Returns (status, bytes). Raises VaultError on 4xx/5xx."""
    hdrs = dict(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:300].decode("utf-8", "replace")
        raise VaultError("%s %s -> HTTP %d: %s"
                         % (method, url.split("?")[0], exc.code, detail))
    except urllib.error.URLError as exc:
        raise VaultError("%s %s -> %s" % (method, url.split("?")[0], exc.reason))


def _json_req(url, method="GET", payload=None, headers=None):
    body = None
    hdrs = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode()
        hdrs["Content-Type"] = "application/json"
    _, raw = _req(url, method, body, hdrs)
    return json.loads(raw or b"{}")


def _config():
    try:
        with open(CONFIG, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_config(cfg):
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, CONFIG)


def _token_path(provider, env, default):
    return os.environ.get(env) or default


def _local_digest(path, kind):
    """Content hash of a local file, in the provider's own algorithm.

    Comparing timestamps across two systems is unreliable - an upload stamps a
    new mtime, clock skew is real, and a re-saved file with identical bytes
    looks like a change. Comparing BYTES is the only test that answers "are
    these the same file".
    """
    try:
        import hashlib
        h = hashlib.new(kind)
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _digest_bytes(data, kind):
    import hashlib
    try:
        return hashlib.new(kind, data).hexdigest()
    except Exception:
        return None


# ------------------------------------------------------------------- providers
class GoogleVault:
    """Google Drive v3 over plain HTTPS."""

    name = "google"
    label = "Google Drive"
    digest = "md5"

    def __init__(self, folder):
        self.folder = folder
        self.path = _token_path("google", "GOOGLE_TOKEN",
                                os.path.expanduser("~/.hermes/google_token.json"))
        self._token = None

    @classmethod
    def configured(cls):
        p = _token_path("google", "GOOGLE_TOKEN",
                        os.path.expanduser("~/.hermes/google_token.json"))
        try:
            with open(p, encoding="utf-8") as fh:
                return bool(json.load(fh).get("refresh_token"))
        except Exception:
            return False

    def _access_token(self):
        if self._token:
            return self._token
        try:
            with open(self.path, encoding="utf-8") as fh:
                tok = json.load(fh)
        except Exception as exc:
            raise VaultError("cannot read Google token at %s (%s)" % (self.path, exc))

        # A token file can look fine and still be dead, so refresh on first use
        # rather than trusting `expiry`.
        if tok.get("refresh_token") and tok.get("client_id") and tok.get("client_secret"):
            form = urllib.parse.urlencode({
                "client_id": tok["client_id"],
                "client_secret": tok["client_secret"],
                "refresh_token": tok["refresh_token"],
                "grant_type": "refresh_token",
            }).encode()
            _, raw = _req("https://oauth2.googleapis.com/token", "POST", form,
                          {"Content-Type": "application/x-www-form-urlencoded"})
            got = json.loads(raw)
            self._token = got["access_token"]
            try:
                tok["token"] = got["access_token"]
                tok["expiry"] = _iso(time.time() + int(got.get("expires_in", 3600)))
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(tok, fh)
                os.replace(tmp, self.path)
            except Exception:
                pass          # writing back is a convenience, not a requirement
            return self._token
        if tok.get("token"):
            self._token = tok["token"]
            return self._token
        raise VaultError("Google token has no refresh_token and no access token")

    def _h(self):
        return {"Authorization": "Bearer %s" % self._access_token()}

    def _find_child(self, parent, name, is_folder):
        q = "name = '%s' and trashed = false" % name.replace("'", "\\'")
        if parent:
            q += " and '%s' in parents" % parent
        if is_folder:
            q += " and mimeType = 'application/vnd.google-apps.folder'"
        url = ("https://www.googleapis.com/drive/v3/files?q=%s&fields=files(id,name)&pageSize=10"
               % urllib.parse.quote(q))
        got = _json_req(url, headers=self._h())
        files = got.get("files") or []
        return files[0]["id"] if files else None

    def ensure_folder(self):
        """Walk the folder path, creating what is missing. Returns the leaf id."""
        parent = None
        for part in [p for p in self.folder.split("/") if p]:
            found = self._find_child(parent, part, True)
            if found:
                parent = found
                continue
            meta = {"name": part,
                    "mimeType": "application/vnd.google-apps.folder"}
            if parent:
                meta["parents"] = [parent]
            made = _json_req("https://www.googleapis.com/drive/v3/files",
                             "POST", meta, self._h())
            parent = made["id"]
        if not parent:
            raise VaultError("no folder configured")
        return parent

    def list(self):
        parent = self.ensure_folder()
        q = "'%s' in parents and trashed = false" % parent
        url = ("https://www.googleapis.com/drive/v3/files?q=%s"
               "&fields=files(id,name,size,modifiedTime,md5Checksum)&pageSize=1000"
               % urllib.parse.quote(q))
        got = _json_req(url, headers=self._h())
        out = {}
        for f in got.get("files") or []:
            out[f["name"]] = {"id": f["id"],
                              "mtime": _parse_iso(f.get("modifiedTime")),
                              "size": int(f.get("size") or 0),
                              "digest": f.get("md5Checksum")}
        return out

    def upload(self, name, data, existing=None):
        parent = self.ensure_folder()
        if existing and existing.get("id"):
            url = ("https://www.googleapis.com/upload/drive/v3/files/%s?uploadType=media"
                   % existing["id"])
            _req(url, "PATCH", data, {**self._h(),
                                      "Content-Type": "application/octet-stream"})
            return
        boundary = "commonai%d" % int(time.time() * 1000)
        meta = json.dumps({"name": name, "parents": [parent]}).encode()
        body = b"".join([
            ("--%s\r\n" % boundary).encode(),
            b"Content-Type: application/json; charset=UTF-8\r\n\r\n",
            meta, b"\r\n",
            ("--%s\r\n" % boundary).encode(),
            b"Content-Type: application/octet-stream\r\n\r\n",
            data, b"\r\n",
            ("--%s--\r\n" % boundary).encode(),
        ])
        url = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart"
        _req(url, "POST", body, {**self._h(),
                                 "Content-Type":
                                 "multipart/related; boundary=%s" % boundary})

    def download(self, remote):
        url = ("https://www.googleapis.com/drive/v3/files/%s?alt=media"
               % remote["id"])
        _, raw = _req(url, headers=self._h())
        return raw


class OneDriveVault:
    """Microsoft Graph over plain HTTPS. Same shape as GoogleVault."""

    name = "onedrive"
    label = "Microsoft OneDrive"
    digest = "sha1"

    def __init__(self, folder):
        self.folder = folder
        self.path = _token_path("onedrive", "ONEDRIVE_TOKEN",
                                os.path.expanduser("~/.hermes/onedrive_token.json"))
        self._token = None

    @classmethod
    def configured(cls):
        p = _token_path("onedrive", "ONEDRIVE_TOKEN",
                        os.path.expanduser("~/.hermes/onedrive_token.json"))
        try:
            with open(p, encoding="utf-8") as fh:
                return bool(json.load(fh).get("refresh_token"))
        except Exception:
            return False

    def _access_token(self):
        if self._token:
            return self._token
        try:
            with open(self.path, encoding="utf-8") as fh:
                tok = json.load(fh)
        except Exception as exc:
            raise VaultError("cannot read OneDrive token at %s (%s)" % (self.path, exc))
        if not (tok.get("refresh_token") and tok.get("client_id")):
            raise VaultError("OneDrive token needs refresh_token and client_id")
        form = urllib.parse.urlencode({
            "client_id": tok["client_id"],
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
            "scope": "https://graph.microsoft.com/.default offline_access",
            **({"client_secret": tok["client_secret"]} if tok.get("client_secret") else {}),
        }).encode()
        tenant = tok.get("tenant", "common")
        url = ("https://login.microsoftonline.com/%s/oauth2/v2.0/token" % tenant)
        _, raw = _req(url, "POST", form,
                      {"Content-Type": "application/x-www-form-urlencoded"})
        got = json.loads(raw)
        self._token = got["access_token"]
        if got.get("refresh_token"):
            try:
                tok["refresh_token"] = got["refresh_token"]
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(tok, fh)
                os.replace(tmp, self.path)
            except Exception:
                pass
        return self._token

    def _h(self):
        return {"Authorization": "Bearer %s" % self._access_token()}

    def _item_url(self, rel=""):
        base = "https://graph.microsoft.com/v1.0/me/drive/root:/%s" % urllib.parse.quote(
            self.folder, safe="/")
        return base + (":/%s" % urllib.parse.quote(rel) if rel else ":")

    def ensure_folder(self):
        """Create the folder path if Graph does not have it. Idempotent."""
        parts = [p for p in self.folder.split("/") if p]
        cur = ""
        for part in parts:
            nxt = (cur + "/" + part) if cur else part
            url = ("https://graph.microsoft.com/v1.0/me/drive/root:/%s"
                   % urllib.parse.quote(nxt, safe="/"))
            try:
                _json_req(url, headers=self._h())
            except VaultError:
                parent = ("https://graph.microsoft.com/v1.0/me/drive/root/children"
                          if not cur else
                          "https://graph.microsoft.com/v1.0/me/drive/root:/%s:/children"
                          % urllib.parse.quote(cur, safe="/"))
                _json_req(parent, "POST", {"name": part, "folder": {}}, self._h())
            cur = nxt
        return self._item_url()

    def list(self):
        url = (self._item_url()
               + "/children?$select=id,name,size,lastModifiedDateTime,file&$top=999")
        got = _json_req(url, headers=self._h())
        out = {}
        for f in got.get("value") or []:
            if f.get("folder"):
                continue
            hashes = (f.get("file") or {}).get("hashes") or {}
            out[f["name"]] = {"id": f["id"],
                              "mtime": _parse_iso(f.get("lastModifiedDateTime")),
                              "size": int(f.get("size") or 0),
                              "digest": hashes.get("sha1Hash")}
        return out

    def upload(self, name, data, existing=None):
        # Simple upload caps at 4 MB; every file here is a text record far below
        # that, so an upload session would be complexity with no caller.
        url = self._item_url(name) + "/content"
        _req(url, "PUT", data, {**self._h(),
                                "Content-Type": "application/octet-stream"})

    def download(self, remote):
        url = ("https://graph.microsoft.com/v1.0/me/drive/items/%s/content"
               % remote["id"])
        _, raw = _req(url, headers=self._h())
        return raw


BACKENDS = {"google": GoogleVault, "onedrive": OneDriveVault}


# ------------------------------------------------------------------- selection
def pick(provider="auto"):
    """Return a configured backend, or explain which ones exist and why not."""
    cfg = _config()
    folder = cfg.get("folder") or DEFAULT_FOLDER
    order = [provider] if provider and provider != "auto" else \
        ([cfg["provider"]] if cfg.get("provider") in BACKENDS else []) + \
        ["google", "onedrive"]

    seen = []
    for name in order:
        cls = BACKENDS.get(name)
        if not cls:
            raise VaultError("unknown provider %r. known: %s"
                             % (name, ", ".join(BACKENDS)))
        if cls.configured():
            return cls(folder)
        seen.append(name)

    raise VaultError(
        "no cloud provider is configured (checked: %s).\n"
        "  google  : needs ~/.hermes/google_token.json with a refresh_token\n"
        "  onedrive: needs ~/.hermes/onedrive_token.json with refresh_token and\n"
        "            client_id, from an Azure app registration with the delegated\n"
        "            scope Files.ReadWrite.All. See README -> Vault." % ", ".join(seen))


# --------------------------------------------------------------------- commands
def cmd_providers():
    cfg = _config()
    print("  vault folder : %s" % (cfg.get("folder") or DEFAULT_FOLDER))
    print("  preference   : %s" % (cfg.get("provider") or "auto"))
    print()
    for name, cls in BACKENDS.items():
        ok = cls.configured()
        print("  %-9s %-18s %s" % (name, cls.label,
                                   "CONFIGURED" if ok else "not configured"))
    print("\n  Files that would move: %d" % len(FILES))
    for f in FILES:
        print("    %s" % f)
    print("  Withheld by default: %s  (--with-assets)" % ", ".join(WITHHELD))
    return 0


def _local(name):
    p = os.path.join(HERE, name)
    if not os.path.exists(p):
        return None
    return {"path": p, "mtime": os.path.getmtime(p),
            "size": os.path.getsize(p)}


def cmd_status(provider):
    be = pick(provider)
    remote = be.list()
    print("  provider : %s  (%s comparison)" % (be.label, be.digest))
    print("  folder   : %s" % be.folder)
    print()
    print("  %-22s %-8s %s" % ("file", "size", "state"))
    print("  " + "-" * 64)
    for name in FILES:
        lo = _local(name)
        re_ = remote.get(name)
        lh = _local_digest(lo["path"], be.digest) if lo else None
        rh = re_.get("digest") if re_ else None
        if not lo and not re_:
            state = "neither side has it"
        elif not re_:
            state = "local only - not backed up"
        elif not lo:
            state = "cloud only - restore will bring it"
        elif lh and rh and lh == rh:
            state = "in sync (same bytes)"
        else:
            newer = "LOCAL" if lo["mtime"] > re_["mtime"] else "CLOUD"
            state = "differs - %s looks newer" % newer
        size = str(lo["size"]) if lo else (str(re_["size"]) if re_ else "-")
        print("  %-22s %-8s %s" % (name, size, state))
    return 0


def cmd_backup(provider, force=False):
    """Push files the cloud does not already hold somewhere newer."""
    be = pick(provider)
    remote = be.list()
    pushed = same = newer = missing = 0
    print("  backing up to %s : %s" % (be.label, be.folder))
    for name in FILES:
        lo = _local(name)
        if not lo:
            missing += 1
            continue
        re_ = remote.get(name)
        lh = _local_digest(lo["path"], be.digest)
        if re_ and lh and re_.get("digest") and lh == re_["digest"]:
            print("    SAME  %-20s already identical in the cloud" % name)
            same += 1
            continue
        if re_ and re_["mtime"] > lo["mtime"] + TOLERANCE and not force:
            print("    SKIP  %-20s cloud copy is newer (%s) - --force to override"
                  % (name, _iso(re_["mtime"])))
            newer += 1
            continue
        with open(lo["path"], "rb") as fh:
            data = fh.read()
        be.upload(name, data, re_)
        print("    UP    %-20s %d bytes" % (name, len(data)))
        pushed += 1
    print("\n  pushed %d | already identical %d | left alone %d | not on this "
          "machine %d" % (pushed, same, newer, missing))
    if newer:
        print("  The files left alone are NEWER in the cloud. Nothing was "
              "overwritten.")
    if same:
        print("  Identical files need no work; the cloud already has these bytes.")
    return 0


def cmd_restore(provider, force=False):
    """Pull files this machine does not already hold somewhere newer."""
    be = pick(provider)
    remote = be.list()
    pulled = same = newer = bad = absent = 0
    print("  restoring from %s : %s" % (be.label, be.folder))
    for name in FILES:
        re_ = remote.get(name)
        if not re_:
            absent += 1
            continue
        lo = _local(name)
        if lo:
            lh = _local_digest(lo["path"], be.digest)
            if lh and re_.get("digest") and lh == re_["digest"]:
                print("    SAME  %-20s already identical here" % name)
                same += 1
                continue
            if lo["mtime"] > re_["mtime"] + TOLERANCE and not force:
                print("    SKIP  %-20s local copy is newer (%s) - --force to override"
                      % (name, _iso(lo["mtime"])))
                newer += 1
                continue
        data = be.download(re_)
        # Verify what arrived against the checksum the cloud published. A
        # truncated download that still parses as JSON is the worst outcome.
        if re_.get("digest"):
            got = _digest_bytes(data, be.digest)
            if got and got != re_["digest"]:
                print("    BAD   %-20s checksum mismatch - NOT written" % name)
                bad += 1
                continue
        dest = os.path.join(HERE, name)
        tmp = dest + ".vault-tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)          # atomic: never a half-written profile
        print("    DOWN  %-20s %d bytes" % (name, len(data)))
        pulled += 1
    print("\n  pulled %d | already identical %d | left alone %d | bad %d | "
          "not in the cloud %d" % (pulled, same, newer, bad, absent))
    if newer:
        print("  The files left alone are NEWER here. Nothing local was replaced.")
    if bad:
        print("  Files marked BAD failed their checksum and were not written.")
    if same:
        print("  Identical files need no work; this machine already has these bytes.")
    return 0


def cmd_init(provider, folder):
    cfg = _config()
    if provider and provider != "auto":
        if provider not in BACKENDS:
            print("  unknown provider %r" % provider)
            return 2
        cfg["provider"] = provider
    if folder:
        cfg["folder"] = folder
    _save_config(cfg)
    print("  wrote %s" % CONFIG)
    print("  provider: %s" % cfg.get("provider", "auto"))
    print("  folder  : %s" % cfg.get("folder", DEFAULT_FOLDER))
    return 0


def main(argv):
    provider = "auto"
    if "--provider" in argv:
        i = argv.index("--provider")
        provider = argv[i + 1] if i + 1 < len(argv) else "auto"
    force = "--force" in argv
    with_assets = "--with-assets" in argv

    try:
        if "--providers" in argv:
            return cmd_providers()
        if "--init" in argv:
            folder = None
            if "--folder" in argv:
                j = argv.index("--folder")
                folder = argv[j + 1] if j + 1 < len(argv) else None
            return cmd_init(provider, folder)
        if "--status" in argv:
            return cmd_status(provider)
        if "--restore" in argv:
            return cmd_restore(provider, force)
        if "--backup" in argv:
            if with_assets:
                for extra in WITHHELD:
                    print("  note: %s is local-only by design; --with-assets is "
                          "accepted but photographs are not uploaded by this "
                          "module. Copy them yourself if you truly want that." % extra)
            return cmd_backup(provider, force)
        print((__doc__ or "").strip().split("Zero dependencies")[0].strip())
        print("\n  run one of: --providers  --status  --backup  --restore  --init")
        return 0
    except VaultError as exc:
        print("  vault: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
