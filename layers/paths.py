"""Where externally-owned modules actually live.

Three of the pieces Common Use AI needs are NOT owned by this repo - they are
symlinked out of ~/scripts into master-ai-cli and .master_ai_scheduled_jobs.
Copying them here would create a second copy of a fact that already has an
owner, which is the drift failure this repo exists to prevent.

So this module resolves them instead: one lookup, no duplicate source.

If a path is listed and missing, callers get None and must degrade loudly -
never silently fall back to a stale local copy.
"""

from pathlib import Path

HOME = Path.home()

# name -> candidate absolute locations, first existing wins
EXTERNAL = {
    "aol_mail": [
        HOME / "projects/master-ai-cli/aol_mail.py",
        HOME / "scripts/aol_mail.py",
    ],
    "gmail_mail": [
        HOME / "projects/master-ai-cli/gmail_mail.py",
        HOME / "scripts/gmail_mail.py",
    ],
    "suggestive_thinking": [
        HOME / ".master_ai_scheduled_jobs/suggestive_thinking.py",
    ],
    "suggestive_thinking_sources": [
        HOME / ".master_ai_scheduled_jobs/suggestive_thinking_sources.py",
    ],
}


def find(name):
    """Return the Path for an externally-owned module, or None if absent."""
    for cand in EXTERNAL.get(name, []):
        if cand.is_file():
            return cand
    return None


def missing():
    """Names that were expected but could not be found anywhere."""
    return [n for n in EXTERNAL if find(n) is None]


if __name__ == "__main__":
    for name in EXTERNAL:
        p = find(name)
        print("  %-30s %s" % (name, p if p else "MISSING"))
