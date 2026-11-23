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
| `sources.py` | Knows where the person's information already lives, and pulls it. |
| `intake.py` | The setup interview. Six sections, branches on situation, resumable, writes `profile.json`. |
| `profile.json` | The single source of truth. Every other file reads from it. |
| `profile.py` | Renders documents from the profile: two resumes and a full-history form. |
| `ledger.py` | Tracks applications. Ages at 90 days, expires at 180, rotates the buckets. |
| `projects.py` | Weekend projects, priced, matched against tools actually owned. |
| `inventory.json` | Tools and project budget (also written by the intake). |
| `ledger.csv` | The applications themselves. |
| `vault.py` | Puts the private files in the owner's own cloud and pulls them back. Google Drive or OneDrive. |
| `backups/` | Snapshots of external documents before they are edited. |

---

## Run it

```bash
python3 sources.py where     # what documents exist and whether they're reachable
python3 sources.py pull      # extract answers into prefill.json (no asking yet)
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

## Prefill: don't ask what's already written down

`sources.py` reads the structured profile, the AI Query rules doc, the Applications Log,
and both resumes, then writes `prefill.json`. `intake.py` shows each pulled answer with
its source and asks only "keep it or correct it?"

On a real profile that took **18 of 36 questions off the table** before the person was
asked anything — identity, job filters, excluded roles, pay floor, commute radius, tools,
budget, GitHub, website.

What it will never prefill: health, household, spending habits, hobbies. Those were never
written down, and a guessed prefill is worse than a question.

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

## The vault: the record survives the machine

`profile.json`, `ledger.csv` and the rest are the whole point of this system, and they
live on one machine. `vault.py` puts them in the owner's **own** cloud storage and can pull
them back onto a clean install — so a dead laptop costs a re-clone, not the record.

```
python3 vault.py --providers    # which backends are configured here
python3 vault.py --status       # local vs cloud, by content hash
python3 vault.py --backup       # push what the cloud does not already have
python3 vault.py --restore      # pull what this machine does not already have
```

**Two providers, one shape.** `google` uses the Drive v3 API with a token already on the
machine. `onedrive` uses Microsoft Graph. Either alone is enough — you do not need both, and
an unconfigured provider reports `not configured` rather than failing the run.

To set up Google Drive, point the vault at a token file with `refresh_token`, `client_id`
and `client_secret` (default `~/.hermes/google_token.json`, or `GOOGLE_TOKEN`), from an
OAuth client with the `drive` scope.

To set up OneDrive, register an app at `portal.azure.com` → App registrations, add the
delegated permission `Files.ReadWrite.All`, and write a token file with `refresh_token`,
`client_id` (and `client_secret` if the app uses one) to
`~/.hermes/onedrive_token.json`, or `ONEDRIVE_TOKEN`. Add `"tenant": "<id>"` for a
single-tenant app; it defaults to `common`.

**The conflict rule.** Local is the source of truth; the cloud is a backup, never a second
owner. `backup` and `restore` compare **content hashes**, not clocks — an upload stamps a
new mtime, so timestamps lie about whether anything actually changed. A file the far side
holds newer is reported and left alone until you pass `--force`. A restore that would
overwrite a newer local edit does not happen quietly; that is the whole failure mode this
rule exists to prevent. Downloads are verified against the checksum the cloud published
before anything is written, and writes are atomic.

**What does not go up.** `assets/` — the wardrobe photographs — is local-only by design.
A person's body photos do not need to be in a cloud account to make a resume better.
Everything else in the vault is text the owner typed about their own life.

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
