# COMMON AI

One person, one profile, and the automation that keeps their life from leaking.

Separate from Tahuti. Nothing here depends on Tahuti and nothing in Tahuti needs to change to use it.

Zero dependencies. Pure Python standard library. No API keys, no network calls, no per-run cost.

---

## The idea

Most people don't need more capability. The bots they already pay for have the capability.
What they need is for somebody to set it up once, and for it to keep working after that
without them nursing it.

So: ask a short set of questions where **every question changes an output**, and everything
else follows from it. A rule that can't change something doesn't get asked — that is the
difference between being taken care of and being interrogated.

---

## The files

| File | What it does |
|---|---|
| `intake.py` | The setup interview. Six sections, branches on situation, resumable, writes `profile.json`. |
| `profile.json` | The single source of truth. Every other file reads from it. |
| `profile.py` | Renders documents from the profile: two resumes and a full-history form. |
| `ledger.py` | Tracks applications. Ages at 90 days, expires at 180, rotates the buckets. |
| `projects.py` | Weekend projects, priced, matched against tools actually owned. |
| `inventory.json` | Tools and project budget (also written by the intake). |
| `ledger.csv` | The applications themselves. |
| `backups/` | Snapshots of external documents before they are edited. |

---

## Run it

```bash
python3 intake.py            # first-time setup, or resume where you stopped
python3 intake.py --status   # which sections are done
python3 intake.py --render   # rewrite profile.json from saved answers
python3 intake.py --reset    # start over (keeps a .bak)

python3 profile.py tenure          # every job against the 90-day rule
python3 profile.py resume trade    # HVAC resume
python3 profile.py resume tech     # AI resume
python3 profile.py form            # full history, for applications and background checks
python3 profile.py gaps            # what's missing or guessed

python3 ledger.py add trade "Trane" "Service Technician"
python3 ledger.py age              # advance the clock
python3 ledger.py report           # the weekly receipt
python3 ledger.py rotation         # which three buckets this week

python3 projects.py this           # this weekend's project
python3 projects.py match          # everything rankable by what you own
```

---

## The rules it enforces

**The 90-day rule.** A job under 90 days never gets a dated line on a resume. Its work folds
into the contract and staffing block instead — real experience, no tenure signal, nothing
misstated. Application forms are the opposite: full history, every date, or you get cut.

**The lifecycle.** An application is live to 89 days, checked at 90, dead at 180. The clock
keeps running whether or not the person is employed, because jobs end.

**The rotation.** Three applications a week across four buckets, one bucket resting. Twelve a
month, no bucket starves, no bucket gets favoritism.

**The health line.** The intake asks what a doctor already decided and plans inside it. It
never decides what is healthy for a condition. Allergies are hard stops that nothing
downstream may override.

---

## Design rules worth keeping

1. **Every question must feed an output.** A question with no consumer is an interrogation.
2. **Anything that can go stale gets a date.** A rule written as a fixed answer becomes a lie
   on a specific day. Compute it, don't store it.
3. **A watchdog must never swallow its own failure.** A broken checker that reports nothing
   looks exactly like a healthy system.
4. **Never hardcode an interpreter path.** They get deleted and the job dies silently.
5. **Don't fight the urge to spend, redirect it.** "Here, on this" beats "don't."

---

## What this is not

Not a hosted service. Not multi-tenant. No billing, no accounts, no isolation between users.
It runs on one machine for one person, and it is honest about that.

`intake.py` writes into `profile.json` but never invents a value. Anything unknown is either
left blank or listed in `_needs_confirmation`, and `profile.py gaps` prints that list every
time you ask.
