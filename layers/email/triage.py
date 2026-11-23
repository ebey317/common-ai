#!/usr/bin/env python3
"""Email triage — sort the inbox into ACT / READ / NOISE without opening bodies.

Usage: triage.py [--days N]
Read-only: shells out to aol_mail.py (IMAP readonly + BODY.PEEK, headers only).
Buckets (checked in this order):
  NOISE — sender/subject matches a known marketing/newsletter hint (whole word).
  ACT   — unread and not noise.
  READ  — recent mail you've already seen and that isn't noise.
Prints three buckets with counts. Takes no action — acting is the
approval box's job. Exits 1 if the inbox could not be fetched.
"""
import re
import subprocess
import sys

import pathlib as _pl
import sys as _sys
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[1]))  # -> layers/
import paths as _paths  # noqa: E402
_AOL = _paths.find("aol_mail")
AOL = str(_AOL) if _AOL else "aol_mail.py"  # falls back to PATH lookup
NOISE_HINTS = (
    # existing
    "newsletter", "unsubscribe", "deals", "sale", "promo", "marketing",
    "linkedin", "ladders", "liberty mutual", "framesdirect", "palm golf",
    # retail / seasonal campaigns
    "black friday", "cyber monday", "limited time", "final days", "act now",
    "discount", "redeem", "your cart", "free shipping", "clearance",
    # lending / insurance / credit marketing
    "pre-approval", "pre approval", "lower your balance", "monthly payments",
    "quote", "quotes", "refinance", "credit score",
    # health / supplement spam
    "cleanse", "detox", "joint health", "fatigue", "bloating", "liver",
    # membership / enrolment pitches
    "enroll", "enrol", "membership", "special offer", "congrats",
)
# Whole-word match so "sale" doesn't fire on "wholesale" / "Salesforce".

# --- homoglyph normalisation ---------------------------------------------
# Bulk mail evades keyword filters by swapping lookalike characters:
# capital I for lowercase l ("BIack Friday"), Cyrillic а/е/о for Latin
# ("FinаnciaI"), and accents ("BéstBuy", "AutoInsurànce"). Matching raw text
# misses every one of them. Normalise first, then match.
_LOOKALIKE = {
    "\u0430": "a", "\u0435": "e", "\u043e": "o", "\u0440": "p",
    "\u0441": "c", "\u0445": "x", "\u0443": "y", "\u0456": "i",
    "\u04bb": "h", "\u0501": "d", "\u0261": "g",
}


def _variants(text: str) -> set[str]:
    """Lowercased forms of text with lookalikes folded, for hint matching."""
    if not text:
        return set()
    t = "".join(_LOOKALIKE.get(ch, ch) for ch in text)
    out = {t.lower()}
    # capital I used in place of lowercase l
    out.add(t.replace("I", "l").lower())
    # accent folding
    try:
        import unicodedata
        out.add("".join(c for c in unicodedata.normalize("NFKD", t)
                        if not unicodedata.combining(c)).lower())
    except Exception:
        pass
    return out


def is_noise(sender: str, subject: str) -> bool:
    """True if any lookalike-normalised variant of sender/subject hits a hint."""
    hay = _variants(sender) | _variants(subject)
    import re as _re
    for hint in NOISE_HINTS:
        pat = r"\b" + _re.escape(hint) + r"\b"
        if any(_re.search(pat, h) for h in hay):
            return True
    return False

NOISE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(h) for h in NOISE_HINTS) + r")\b", re.I)
# Senders whose unread mail should surface as ACT. Empty = every unread,
# non-noise message is ACT (the old behaviour).
# Populated from the protected categories in the email-triage standing order:
# probation, government/court/legal, grants, anything with Kelly in it - plus
# live interview and recruiter threads. Non-empty means only these surface as
# ACT; everything else unread falls to READ instead of shouting.
ACT_SENDERS: tuple[str, ...] = (
    # probation / legal / government
    "jacqueline", "hughey", "indy.gov", ".gov", "court", "warrant", "legal",
    # grants
    "grant", "foundation", "sbir", "funding",
    # Kelly engineering
    "kelly",
    # live interviews and recruiters
    "incertec", "ellery", "bestaff", "hardee", "wendy", "culver",
    "aerotek", "indotronix", "caplinger", "techpro", "beeson",
    "Example Employer", "aegis", "axion", "ams mechanical", "ncw",
    # job boards
    "indeed", "ziprecruiter", "linkedin.com/jobs",
)
# aol_mail.py data rows start with a numeric UID; its banner/header/"No
# messages found." lines do not, so this keeps only real messages.
ROW_RE = re.compile(r"^(\d+)\s+\S")


def parse_rows(text: str) -> dict[str, str]:
    """Map UID -> display row, keeping only real message rows."""
    rows: dict[str, str] = {}
    for line in text.splitlines():
        m = ROW_RE.match(line)
        if m:
            rows[m.group(1)] = line
    return rows


def classify(uid: str, row: str, unread_uids: set[str]) -> str:
    if is_noise(row, ""):
        return "NOISE"
    if uid in unread_uids and (
            not ACT_SENDERS or any(s in row.lower() for s in ACT_SENDERS)):
        return "ACT"
    return "READ"


def _fetch(days: str, unread: bool) -> dict[str, str] | None:
    cmd = [sys.executable, AOL, "--days", days]
    if unread:
        cmd.append("--unread")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        print("inbox fetch failed: timed out after 60s", file=sys.stderr)
        return None
    if r.returncode != 0:
        detail = r.stderr.strip()[-300:] or "no error output"
        print(f"inbox fetch failed (exit {r.returncode}): {detail}",
              file=sys.stderr)
        return None
    return parse_rows(r.stdout)


def main() -> int:
    days = "2"
    args = sys.argv[1:]
    if "--days" in args:
        try:
            days = str(max(1, min(7, int(args[args.index("--days") + 1]))))
        except Exception:
            pass
    unread = _fetch(days, unread=True)
    recent = _fetch(days, unread=False)
    if unread is None or recent is None:
        return 1
    rows = {**recent, **unread}  # union by UID: old unread can exceed the cap
    unread_uids = set(unread)
    buckets: dict[str, list[str]] = {"ACT": [], "READ": [], "NOISE": []}
    for uid in sorted(rows, key=int, reverse=True):
        buckets[classify(uid, rows[uid], unread_uids)].append(rows[uid])
    for i, (name, items) in enumerate(buckets.items()):
        print(("\n" if i else "") + f"=== {name} ({len(items)}) ===")
        print("\n".join(items) if items else "(none)")
    print(f"\n=== total listed: {len(rows)} "
          f"(unread: {len(unread_uids)}) ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
