#!/usr/bin/env python3
"""
COMMON AI - Google Workspace
============================
Two jobs, and they are different products.

  check      is the configuration healthy? (the thing people pay a one-time
             fee for, because it silently breaks every seven days)
  organize   what is actually messy in there? (the thing worth paying monthly,
             because it goes messy again)

  python3 workspace.py check
  python3 workspace.py organize            # read-only report
  python3 workspace.py organize --json

CONFIGURATION IS THE HARD PART, NOT THE CLICKING. A token can pass a file check
and still be dead; an API can be enabled or not; a scope can be missing so one
service works and another 403s. check() probes each service live and says which
of those is true, because "it's set up" and "it works" are different sentences.

ORGANIZE NEVER MOVES ANYTHING. It reports. Moving is sensei_clean's job, behind
its own apply and undo.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date

TOKEN = os.path.expanduser("~/.hermes/google_token.json")
FOLDER_MIME = "application/vnd.google-apps.folder"
DOC_MIME = "application/vnd.google-apps.document"
TESTING_CAP_DAYS = 7


def _token():
    try:
        with open(TOKEN, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _svc(name, version):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    d = _token()
    if not d:
        return None
    creds = Credentials(
        token=d.get("token"),
        refresh_token=d.get("refresh_token"),
        token_uri=d.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=d.get("client_id"),
        client_secret=d.get("client_secret"),
        scopes=d.get("scopes"),
    )
    return build(name, version, credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------- check
def check():
    rows = []
    verdict = {"ok": 0, "degraded": 0, "broken": 0}

    d = _token()
    if not d:
        print("BROKEN: no token at %s" % TOKEN)
        print("  -> authorise Google once via the google-workspace skill")
        return 1

    age_days = (date.today() -
                date.fromtimestamp(os.path.getmtime(TOKEN))).days
    has_refresh = bool(d.get("refresh_token"))
    scopes = [s.split("/")[-1] for s in d.get("scopes", [])]

    rows.append(("token file", "ok" if has_refresh else "broken",
                 "refresh token present" if has_refresh else "no refresh token - dies on next refresh"))
    state = "ok"
    if age_days >= TESTING_CAP_DAYS:
        state = "broken"
    elif age_days >= TESTING_CAP_DAYS - 2:
        state = "degraded"
    rows.append(("token age", state,
                 "%d days old%s" % (age_days,
                                    "  <- Testing mode kills at ~7, re-authorise now"
                                    if state != "ok" else "")))

    probes = [
        ("drive", "drive", "v3", lambda s: s.files().list(pageSize=1).execute()),
        ("gmail", "gmail", "v1",
         lambda s: s.users().getProfile(userId="me").execute()),
        ("calendar", "calendar", "v3",
         lambda s: s.calendarList().list(maxResults=1).execute()),
    ]
    for label, api, ver, call in probes:
        try:
            s = _svc(api, ver)
            if s is None:
                rows.append((label, "broken", "could not build client"))
                continue
            call(s)
            rows.append((label, "ok", "live round-trip succeeded"))
        except Exception as exc:
            msg = str(exc)
            short = "403 - API not enabled or scope missing" if "403" in msg \
                else ("401 - token rejected" if "401" in msg else msg[:60])
            rows.append((label, "broken", short))

    # Docs and Sheets deserve a real probe, not a Drive listing. Enumerating a
    # document through Drive says the DRIVE API works; it says nothing about
    # whether the Docs API is enabled or its scope granted. So find one real
    # file, then call the service that would actually be used.
    try:
        s = _svc("drive", "v3")
        doc = s.files().list(q="mimeType='%s'" % DOC_MIME, pageSize=1,
                             fields="files(id)").execute()
        found = doc.get("files") or []
        if not found:
            rows.append(("docs", "degraded",
                         "no document to probe - Docs API unverified"))
        else:
            ds = _svc("docs", "v1")
            if ds is None:
                rows.append(("docs", "broken", "could not build docs client"))
            else:
                ds.documents().get(
                    documentId=found[0]["id"], fields="documentId").execute()
                rows.append(("docs", "ok", "live documents.get succeeded"))
    except Exception as exc:
        rows.append(("docs", "broken", str(exc)[:60]))

    try:
        s = _svc("drive", "v3")
        sh = s.files().list(
            q="mimeType='application/vnd.google-apps.spreadsheet'",
            pageSize=1, fields="files(id)").execute()
        found = sh.get("files") or []
        if not found:
            rows.append(("sheets", "degraded",
                         "no spreadsheet to probe - Sheets API unverified"))
        else:
            ss = _svc("sheets", "v4")
            if ss is None:
                rows.append(("sheets", "broken", "could not build sheets client"))
            else:
                ss.spreadsheets().get(spreadsheetId=found[0]["id"]).execute()
                rows.append(("sheets", "ok", "live spreadsheets.get succeeded"))
    except Exception as exc:
        rows.append(("sheets", "broken", str(exc)[:60]))

    print("=" * 70)
    print("  GOOGLE WORKSPACE - CONFIGURATION")
    print("=" * 70)
    for name, state, note in rows:
        verdict[state] += 1
        print("  %-14s %-9s %s" % (name, state.upper(), note))

    print("\n  scopes: %s" % ", ".join(scopes))
    print("\n" + "-" * 70)
    print("  %d ok | %d degraded | %d broken"
          % (verdict["ok"], verdict["degraded"], verdict["broken"]))
    if verdict["broken"]:
        print("  A broken service fails silently in most tools. That is why this")
        print("  check exists and why the watchdog runs daily, not weekly.")
    else:
        print("  Configuration is sound. The watchdog keeps it that way.")
    return 1 if verdict["broken"] else 0


# ---------------------------------------------------------------- organize
def _name_key(name):
    n = (name or "").strip().strip("\"'").strip()
    return " ".join(n.lower().split())


def organize(as_json=False):
    s = _svc("drive", "v3")
    if s is None:
        print("no usable token - run: python3 workspace.py check")
        return 1

    items, token = [], None
    try:
        while True:
            resp = s.files().list(
                q="trashed = false",
                fields="nextPageToken, files(id,name,mimeType,size,"
                       "modifiedTime,parents,webViewLink)",
                pageToken=token, pageSize=200,
                supportsAllDrives=True, includeItemsFromAllDrives=True,
            ).execute()
            items.extend(resp.get("files", []))
            token = resp.get("nextPageToken")
            if not token:
                break
    except Exception as exc:
        print("drive enumerate failed: %s" % exc)
        return 1

    # duplicate names under the same parent
    by_name = defaultdict(list)
    for f in items:
        key = _name_key(f.get("name"))
        if not key:
            continue
        for p in (f.get("parents") or ["root"]):
            by_name[(p, key)].append(f)
    dup_names = {k: v for k, v in by_name.items() if len(v) > 1}

    # empty documents
    docs = [f for f in items if f.get("mimeType") == DOC_MIME]
    empty_docs = [f for f in docs if int(f.get("size") or 0) == 0]

    folders = [f for f in items if f.get("mimeType") == FOLDER_MIME]
    files = [f for f in items if f.get("mimeType") != FOLDER_MIME]

    if as_json:
        print(json.dumps({
            "total": len(items), "folders": len(folders), "files": len(files),
            "duplicate_name_groups": len(dup_names),
            "empty_documents": len(empty_docs),
            "groups": [{"name": k[1], "count": len(v),
                        "ids": [x["id"] for x in v]} for k, v in dup_names.items()],
        }, indent=2))
        return 0

    print("=" * 70)
    print("  GOOGLE DRIVE - WHAT IS ACTUALLY MESSY")
    print("=" * 70)
    print("\n  %d items  |  %d folders  |  %d files  |  %d documents"
          % (len(items), len(folders), len(files), len(docs)))

    print("\n  DUPLICATE NAMES  %d group(s)" % len(dup_names))
    for (parent, key), group in sorted(dup_names.items(),
                                       key=lambda kv: -len(kv[1]))[:12]:
        raw = [g.get("name") for g in group]
        print("    %-40s %d" % (key[:40], len(group)))
        for r in raw[:4]:
            print("        %r" % r)

    print("\n  EMPTY DOCUMENTS  %d" % len(empty_docs))
    for f in empty_docs[:8]:
        print("    %s" % (f.get("name") or "(untitled)")[:56])

    print("\n" + "-" * 70)
    print("  This report moves nothing. `sensei-clean scan` + apply does that,")
    print("  with undo. Organization you can't reverse isn't organization.")
    return 0


def main(argv):
    if len(argv) > 1 and argv[1] == "check":
        return check()
    if len(argv) > 1 and argv[1] == "organize":
        return organize("--json" in argv)
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
