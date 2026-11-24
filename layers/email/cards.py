#!/usr/bin/env python3
"""Email cards: every account, one set of cards by category.

Usage: cards.py [--limit N] [--accounts gmail,aol,...] [--json]

READ-ONLY. Uses the email bridge's own IMAP helpers (~/scripts/email_mcp/server.py):
mailbox opened readonly, headers fetched with BODY.PEEK. It never opens a message
body, moves, marks or deletes anything. Acting is the owner's call.

Cards, in the order they are checked for each message:
  JOB LEADS  job-board alerts and recruiter/employer mail
  IMPORTANT  government, court, probation, grants, interviews - mail that needs you
  BILLS      statements, invoices, payment due, receipts
  SOCIAL     LinkedIn/Facebook/etc. that is not a job alert
  PERSONAL   a human address at a free-mail provider (gmail/aol/yahoo...), not bulk
  SPAM       marketing, lookalike-character offers, insurance, supplements
  OTHER      company mail that fits nothing above, so nothing is hidden

Mail from a person at a job board (e.g. an Indeed message from a hiring manager)
is IMPORTANT, not a bulk job alert.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.expanduser("~/scripts/email_mcp"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402  (the email bridge; fastmcp is only loaded when serving)
import triage  # noqa: E402  (is_noise: lookalike-aware marketing hints)

CARDS = ("important", "bills", "job", "personal", "social", "spam", "unsorted")
LABEL = {"important": "IMPORTANT", "bills": "BILLS", "job": "JOB LEADS",
         "personal": "PERSONAL", "social": "SOCIAL", "spam": "SPAM & PROMOS",
         "unsorted": "OTHER"}
# Cards that list every message. Spam only gets a count and a few senders.
LISTED = ("important", "bills", "job", "personal", "social", "unsorted")

JOB_SENDERS = ("indeed", "ziprecruiter", "jobalert", "jobalerts", "glassdoor",
               "monster", "careerbuilder", "linkedin job", "jobs-noreply")
JOB_WORDS = ("interview", "application", "applied", "hiring", "your resume",
             "job alert", "new jobs", "now hiring", "position", "recruiter")
IMPORTANT_SENDERS = triage.ACT_SENDERS  # probation, .gov, courts, grants, live employers
# These job-board words mean "a person wrote to you", not "an alert went out".
HUMAN_JOB = ("ready to hear more", "interview", "invite", "scheduled", "offer",
             "next step", "your application", "moving forward")
BILL_WORDS = ("statement", "payment due", "past due", "invoice", "receipt",
              "autopay", "bill is ready", "your bill", "amount due", "payment received",
              "payment confirmation", "balance due")
SOCIAL_SENDERS = ("linkedin", "facebook", "instagram", "twitter", "x.com",
                  "tiktok", "reddit", "nextdoor", "discord", "pinterest", "snapchat")
AUTOMATED = server._AUTOMATED_LOCAL_PARTS


def _fold(text):
    """Lookalike-folded lowercase variants (Cyrillic, capital-I-for-l, accents)."""
    return triage._variants(text)


def _local(sender):
    m = server._SENDER_ADDR_RE.search(sender.strip())
    return (m.group(1) if m else "").lower()


FREE_MAIL = ("gmail.com", "aol.com", "yahoo.com", "outlook.com", "hotmail.com",
             "icloud.com", "live.com", "msn.com", "me.com", "proton.me", "protonmail.com")
INTERVIEW_WORDS = ("interview", "schedule an", "schedule your", "next step",
                   "ready to hear more", "moving forward", "job offer", "offer letter",
                   "background check", "drug screen", "onboarding")
EXTRA_SPAM = ("insurance", "glp", "% off", "pre-approval", "preapproval", "extracash",
              "cash advance", "life insurance", "free quote", "medicare", "knock knock",
              "partner")
JOB_EXTRA = ("staffing", "weekly jobs", "jobs update", "your application",
             "application is complete", "application was viewed", "recruiting",
             "complete your form", "message from")
_HIDDEN_CH = re.compile(r"[\u034f\u200b-\u200f\u2060\ufeff\u00ad]")
_PADDED = re.compile(r"\S {3,}\S")


def _address(sender):
    m = re.search(r"<?([^<>\s]+@[^<>\s]+?)>?\s*$", sender.strip())
    return m.group(1).lower() if m else ""


def classify(sender, subject):
    s_all = " ".join(_fold(sender))
    t_all = " ".join(_fold(subject))
    addr = _address(sender)
    domain = addr.rsplit("@", 1)[-1]
    is_job_board = any(j in s_all for j in JOB_SENDERS)
    obfuscated = server._looks_obfuscated(subject) or server._looks_obfuscated(sender)
    # invisible characters, padded spacing and +tags are bulk-mail disguises
    display = sender.split("<")[0]
    disguised = bool(_HIDDEN_CH.search(display + subject) or _PADDED.search(display)
                     or addr.split("@")[0].startswith("boss+"))
    if (obfuscated or disguised) and not is_job_board:
        return "spam"
    # a person or employer asking for something outranks every bulk rule
    if any(w in t_all for w in INTERVIEW_WORDS) and not triage.is_noise("", subject):
        return "important"
    if is_job_board or ("linkedin" in s_all and any(w in t_all for w in JOB_WORDS)) \
            or any(w in s_all + " " + t_all for w in JOB_EXTRA):
        return "job"
    if any(b in t_all for b in BILL_WORDS) and not triage.is_noise("", subject):
        return "bills"
    if any(k in s_all for k in SOCIAL_SENDERS):
        return "social"
    if any(k in s_all for k in IMPORTANT_SENDERS if k and k not in
           ("indeed", "ziprecruiter", "linkedin.com/jobs")):
        return "important"
    if triage.is_noise(sender, subject) or any(w in s_all + " " + t_all for w in EXTRA_SPAM):
        return "spam"
    automated = any(a in _local(sender) for a in AUTOMATED) or \
        server._looks_automated_sender(sender)
    # personal = a human address at a free-mail provider; company mail is "other"
    if domain in FREE_MAIL and not automated:
        return "personal"
    return "unsorted"


def fetch(account, limit):
    acct = server.get_account(account)
    conn = server.imap_connect(acct)
    try:
        conn.select("INBOX", readonly=True)
        _, data = conn.search(None, "ALL")
        seqs = data[0].split()[-limit:][::-1]
        return server.fetch_headers_batch(conn, seqs)
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def short(text, n):
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def sender_name(sender):
    name, _ = server.parseaddr(sender)
    return name.strip('" ') or sender


def main(argv):
    limit = 40
    if "--limit" in argv:
        limit = max(1, min(100, int(argv[argv.index("--limit") + 1])))
    names = None
    if "--accounts" in argv:
        names = argv[argv.index("--accounts") + 1].split(",")
    if names is None:
        names = list(server.load_credentials().get("accounts", {}))

    cards = {c: [] for c in CARDS}
    failed = []
    for acc in names:
        try:
            rows = fetch(acc, limit)
        except Exception as exc:  # one dead account must not hide the others
            failed.append((acc, str(exc)[:120]))
            continue
        for r in rows:
            cards[classify(r["from"], r["subject"])].append({**r, "account": acc})

    if "--json" in argv:
        print(json.dumps({"cards": cards, "failed": failed}, indent=1))
        return 0

    total = sum(len(v) for v in cards.values())
    print("INBOX CARDS  (%d messages, %d accounts)" % (total, len(names) - len(failed)))
    for c in CARDS:
        items = cards[c]
        if not items and c in ("unsorted",):
            continue
        print("\n%s  %d" % (LABEL[c], len(items)))
        if c in LISTED:
            groups = {}
            for r in items:
                groups.setdefault((r["account"], sender_name(r["from"])), []).append(r)
            for (acc, who), rs in groups.items():
                if len(rs) > 2:
                    print("  - [%s] %s: %d messages, latest: %s" % (
                        acc, short(who, 28), len(rs), short(rs[0]["subject"], 50)))
                else:
                    for r in rs:
                        print("  - [%s] %s: %s" % (acc, short(who, 28),
                                                   short(r["subject"], 70)))
        elif items:
            senders = []
            for r in items:
                n = short(sender_name(r["from"]), 24)
                if n not in senders:
                    senders.append(n)
            print("  e.g. " + ", ".join(senders[:4]))
    for acc, why in failed:
        print("\n%s COULD NOT BE READ: %s" % (acc.upper(), why))
    return 1 if failed and len(failed) == len(names) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
