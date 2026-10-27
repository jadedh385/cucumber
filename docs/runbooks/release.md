# Runbook · Releasing a version to production

**For:** Claude with the Owner, from the Owner's Mac. **Why:** the commands
behind the [release process](../roadmap/release-process.md) and the G6 gate
([gates.md](../roadmap/gates.md#g6--release)). **Machines:** staging is the
Asus (`ssh cucumber-staging`), production is the MacBook (`ssh cucumber-server`),
both set up by their runbooks ([Asus](asus-staging-setup.md),
[MacBook Phase 3](macbook-server-setup.md#phase-3--production-copy-claude-over-ssh-30-min)).

Scripts always run from `~/cucumber/tools` (a clone on `main`), never from
`src`. **Type the commands in an `ssh -t` session** (`ssh -t cucumber-staging`,
`ssh -t cucumber-server`): only a login shell has `uv` and `docker` on its
path (on the MacBook they live in `/opt/homebrew/bin` and `/usr/local/bin`),
and the deploy command may ask a question, which needs a keyboard (no
keyboard = "no").
Each step's output goes into the unit's G6 note as evidence.

## Before starting

- Every pull request for this release is merged, and `main`'s CI is green.
- Lab is quiet (release-process.md: outside busy lab hours, at most once a week).
- Note what each machine runs now: `cat ~/cucumber/staging/current` on the
  Asus, `cat ~/cucumber/production/current` on the MacBook (missing before the
  first release). That is what a rollback goes back to.
- **First release with U0.5 (accounts) only:** run the
  [accounts check](#accounts-check-first-release-with-u05) on staging and
  on production. Migration `accounts 0003` refuses to run while any account
  breaks its rules, and the deploy would stop half-way (U0.5 G4, H1).
- **First release with U0.6 (roles) only:** run the
  [roles check](#roles-check-first-release-with-u06) on staging and on
  production. Migration `accounts 0006` refuses to run while any account
  breaks the one-role rule (U0.6 G4).

## Accounts check (first release with U0.5)

U0.5 adds two rules to `auth_user`: the user name is the lowercase email
(the same as `email`), and no account has the superuser or staff flag.
Migration `accounts 0003` checks first and stops with a list of the accounts
that break them. Nothing is lost when it stops, but by then migrations 0001
and 0002 have already run, and the deploy puts the old version back. So
check before deploying, on each machine (`staging`, then `production`):

```bash
cd ~/cucumber/<staging|production>/src
export IMAGE_NAME=cucumber-<staging|production> CUCUMBER_VERSION="$(cat ../current)"
dc() { docker compose -p cucumber-<staging|production> --env-file ../secrets.env -f deploy/compose.server.yaml "$@"; }
dc exec -T db psql -U postgres -d cucumber -c "
  SELECT id, username, email, is_superuser, is_staff FROM auth_user
  WHERE NOT (username = lower(btrim(username)) AND email = username
             AND username LIKE '%_@_%')
     OR is_superuser OR is_staff;"
```

**No rows: go on with step 1.** Each row is an account to fix first. The
Owner runs the fix (production changes are the Owner's), with Claude
writing the line for that account:

```bash
dc exec -T db psql -U postgres -d cucumber -c "
  UPDATE auth_user SET username = '<email, lowercase>', email = '<email, lowercase>',
         is_superuser = false, is_staff = false
  WHERE id = <id>;"
```

Then run the check again. After the release, give the Owner's account the
Admin role and a password: [Admin account](#admin-account-the-first-one-or-a-rescue).

## Roles check (first release with U0.6)

U0.6 allows one role per account, and every group is a role (`admin`,
`supervisor`, `tech`, `read_only`). Migration `accounts 0006` checks first and
stops with a list of accounts in more than one group, in a group that isn't
a role, or whose user name isn't its own normalised email. Nothing is lost
when it stops: only `accounts 0005` has run by then (it adds three empty
groups), and the deploy puts the old version back. Check before deploying,
on each machine, with `dc` set as in the accounts check above:

```bash
dc exec -T db psql -U postgres -d cucumber -c "
  SELECT u.id, u.username, g.name AS grp FROM auth_user u
  JOIN auth_user_groups ug ON ug.user_id = u.id
  JOIN auth_group g ON g.id = ug.group_id
  WHERE g.name NOT IN ('admin', 'supervisor', 'tech', 'read_only')
     OR u.id IN (SELECT user_id FROM auth_user_groups
                 GROUP BY user_id HAVING count(*) > 1)
  ORDER BY u.username, g.name;"
```

**No rows: go on with step 1.** Each row is a group to take off an account
(keep one role each). The Owner runs the fix, with Claude writing the line:

```bash
dc exec -T db psql -U postgres -d cucumber -c "
  DELETE FROM auth_user_groups
  WHERE user_id = <id> AND group_id = (SELECT id FROM auth_group WHERE name = '<group>');"
```

Then run the check again. An account left with no role can be given one on
its Staff page after the release. (The user-name check is the
[accounts check](#accounts-check-first-release-with-u05), already passed
with U0.5.)

## 1. Draft (Claude)

```bash
gh workflow run "Draft release" --ref main
gh run watch "$(gh run list --workflow "Draft release" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh release list --limit 3                     # the new draft and its version, e.g. 2026.10.1
```

Run the workflow **once**. A second run makes a second draft with the next number
at the same commit (U0.9 G6, finding 1). Check `gh release list` before running
it again, and delete a stray draft with `gh release delete <version> --cleanup-tag`.

## 2. Wording (Owner)

On GitHub → Releases → the draft → Edit. Fix the **For staff** wording
([template](../roadmap/release-process.md#staff-note-template)). "None" there
means the Discord hook posts nothing. **Don't press Publish yet.**

## 3. Rehearse on staging (Claude)

```bash
ssh -t cucumber-staging
cd ~/cucumber/tools && git pull
uv run --no-dev python -m scripts.deploy staging <version>     # the release
uv run --no-dev python -m scripts.deploy staging <before>      # back to what ran before
uv run --no-dev python -m scripts.deploy staging <version>     # and forward again
```

Each must end in `Done: staging now runs …`. This is G6's "rollback rehearsed
on staging". If a step fails, stop: the draft stays a draft.

**A release with migrations can't be rehearsed this way.** The older version
doesn't know the new migrations, so the second command stops at "The database
has N changes this version doesn't know … Restore an older copy instead, or
type yes to go on". Don't type yes: the old code would run on a database it
doesn't fit (for U0.7, whose audit triggers refuse its writes). Rehearse the
restore instead, with the copy the first command took:
[Restore a copy](#restore-a-copy-production) with `staging` in place of
`production`, then deploy the release forward again. (U0.7 shipped without
this rehearsal, as an Owner exception: [U0.7 G6](../roadmap/units/u0.7-g6-release.md);
U0.8 did it: [U0.8 G6](../roadmap/units/u0.8-g6-release.md).)

**If G5 already put the migrations on staging** (a `--source` deploy of the
branch), the tag's deploy says "Updating the database (no changes)" and its copy
already holds them, so restoring that copy doesn't show the way back from
production's state. Also restore the copy G5's deploy took (the one before the
`source-…` build), check `pending_migrations` lists the release's migrations and
`unknown` is empty, leave the app stopped, then deploy the tag forward: that
run applies the migrations for real, as production will. Check the app on
`APP_PORT` from `secrets.env`, not 8000. (Worked through for U0.8 and again for
U0.9: [U0.9 G6](../roadmap/units/u0.9-g6-release.md).)

**No output for more than a minute** means the command is waiting at a
question like that one. A session without a keyboard can't answer it, so
stop it (nothing has changed before the database check) and run it again in
an `ssh -t` session to read the question.

## 4. Deploy to production (Claude)

```bash
ssh -t cucumber-server
cd ~/cucumber/tools && git pull
uv run --no-dev python -m scripts.deploy production <version>
```

**U0.7 only: stop the app before the deploy** (`dc stop app`, as in the
restore steps below). While `migrate` runs, the old version's writes to the
audited tables are refused, and the 5-second `lock_timeout` can abort core 0006.
The business is not yet relying on the app, so a short outage is fine. Do it
on staging first.

**U0.8 too: stop the app before the deploy** (`dc stop app`). U0.8's
`plants 0003` and `core 0007` give up after 5 seconds if a request holds their
table. With the app stopped nothing can, and if the deploy does stop and says
to restore, nothing saved after the copy is lost (U0.8 design §16, D1, Owner
2026-10-24). Do it on staging first.

**U0.9 too: stop the app before the deploy** (`dc stop app`), staging first. The
undo of `references 0008` refuses once anything uses or changes the lists, so the
copy the deploy takes is the way back, and nothing saved after it should be lost
([U0.9 G6](../roadmap/units/u0.9-g6-release.md)).

**U0.7 only: everyone is signed out once.** The new login backend
(`AuditedRehashBackend`) replaces the old one, and Django ends any session made
through a backend that is no longer listed. Each person logs in again after the
release; nothing else is lost. Tell staff beforehand.

Production takes **version tags only** (AC11). The command takes the
database copy first, migrates, starts the app and checks `/health/`. If the
check fails it puts the previous version back by itself (AC12) and says so;
then stop, and the draft stays a draft.

## 5. Check the copy reads (Claude)

The backup "verified" for G6: the copy the deploy just took is complete.

```bash
ssh -t cucumber-server
cd ~/cucumber/production/src
export IMAGE_NAME=cucumber-production CUCUMBER_VERSION="$(cat ../current)"
dc() { docker compose -p cucumber-production --env-file ../secrets.env -f deploy/compose.server.yaml "$@"; }
copy=$(ls -t ../backups/*.dump | head -1); echo "$copy"
dc exec -T db pg_restore --list < "$copy" | grep -c "TABLE DATA"   # a number, no error
```

## 6. Smoke test (Claude)

The app listens on the MacBook only, and expects its public name and HTTPS
from Cloudflare, so the check sends both, as the deploy command does:

```bash
ssh -t cucumber-server
h=(-H "Host: cucumber.southeastcanopy.com" -H "X-Forwarded-Proto: https")
curl -s "${h[@]}" http://127.0.0.1:8000/health/                                  # ok
curl -s -o /dev/null -w '%{http_code}\n' "${h[@]}" http://127.0.0.1:8000/accounts/login/   # 200
curl -s "${h[@]}" http://127.0.0.1:8000/accounts/login/ | grep -c "Practice"     # 0: no banner on production (AC9)
cd ~/cucumber/tools && uv run --no-dev python -m scripts.flag production list    # runs as cucumber_app (AC13)
```

If the release brings a feature behind a flag, switch it on now (Owner
first if wanted: `--group admin`) and try it, as the G6 line says.

## 7. Publish (Owner)

GitHub → Releases → the draft → **Publish release**. That means "it's live".
Then Claude checks the hook:

```bash
gh run list --workflow "Announce release" --limit 1      # green
```

The run log says "posted" or "Nothing for staff in <version>, so nothing was
posted". If Discord failed, the release still stands: the Owner posts the
staff note by hand.

## If something goes wrong

- **Deploy failed, previous version back:** nothing to undo. Read the 30
  log lines the command printed; fix in a pull request; draft again later.
- **Deploy stopped and says to restore:** the migrations no longer match the
  previous version. Restore the copy from step 4 with the steps below, with
  Claude.
- **Wrong wording after publishing:** edit the release on GitHub; Discord
  keeps the first post, so post a short correction there.
- **Deploy stopped at "The database's protections are not all on"**: see
  [the protections check](#the-protections-check-u07) below; for a number
  generator, [Number generator behind](#number-generator-behind).
- **Deploy stopped at "canceling statement due to lock timeout"** (U0.8's
  `plants 0003` or `core 0007`): something held a table for over 5 seconds
  (the app should be stopped for U0.8, see §4; check `dc ps`), and that
  migration gave up without changing anything. The U0.8 migrations before it
  may already be made, and then the deploy says to restore: keep the app
  stopped, restore, find what held the table, then deploy again.

## The protections check (U0.7)

From U0.7 every deploy runs `cucumber_check_guards` twice: before the copy
(step 3b) and after migrating (step 5b). It checks the append-only, reason and
audit triggers, their functions, `cucumber_app`'s grants and the app role
itself, and lists anything missing, switched off or changed, one line each.
Run it by hand the same way, on the server:

```bash
ssh -t cucumber-staging            # or cucumber-server for production
cd ~/cucumber/<staging|production>/src
export IMAGE_NAME=cucumber-<staging|production> CUCUMBER_VERSION="$(cat ../current)"
dc() { docker compose -p cucumber-<staging|production> --env-file ../secrets.env -f deploy/compose.server.yaml "$@"; }
dc run --rm migrate python manage.py cucumber_check_guards
```

- **Stopped before the copy (3b):** nothing changed and the old version still
  runs. A line that says a table **was truncated** means someone emptied a
  protected table as the database owner. If that was you (on staging, a
  practice-data reset), accept it, saying why, then deploy again:

  ```bash
  dc run --rm migrate python manage.py cucumber_check_guards --accept "staging reset with practice data"
  ```

  If nobody meant to, don't accept: on production, restore the copy from
  before it happened, with Claude. Any other line (a trigger disabled, a
  grant added) means the database was changed by hand: stop, and look at it
  with Claude before going on.
- **Stopped after migrating (5b):** the database was updated, but the new
  version's own migration broke a protection. The app was not restarted, so
  the previous version still runs, against a database it may not fit. Restore
  the copy the command names, with Claude, and fix the migration in a pull
  request. CI runs the same check, so this should never reach a server.
- **To read the trail:** `dc exec -T app python manage.py cucumber_audit`
  (`--person`, `--table`, `--row`, `--since`, `--until`, `--limit`). People are
  shown by id; look the id up on the Staff page.

### Number generator behind

From U0.8 the check also reads each number generator (`plants`, `batches`,
`events`). A line like `plants: the next new one would get id 43, but id 50
is already used` means the next new plant would be refused, because its
number is taken. **Find out why first:** a restore from an older copy, or
someone resetting the generator by hand. Look at it with Claude; don't just
move it on.

Once the cause is known, the Owner moves the generator past the highest id,
as the owner, through the migrate service (put the table's name in both
places):

```bash
dc run --rm migrate python manage.py shell -c "
from django.db import connection
connection.cursor().execute(\"SELECT setval('public.plants_id_seq', (SELECT max(id) FROM plants))\")
"
dc run --rm migrate python manage.py cucumber_check_guards     # no line for plants now
```

A generator ahead of its rows (a gap) is fine and needs nothing (U0.8 AC9).

### Only `cucumber_owner` may supply an id

From U0.8 a new plant, batch or event takes its id from the database. Any
SQL that gives one itself (`INSERT INTO plants (id, …)`) is refused with
`plants_id_from_sequence`, except when it runs as `cucumber_owner`, as the
V.2 import does (it keeps plant numbers already in use). That includes the
`postgres` superuser the UAT scripts use: on purpose (U0.8 design §5.1,
review L4). Leave `id` out and let the database give it. Nobody, the owner
included, can change an existing id (`plants_id_fixed`, `batches_id_fixed`).

## Admin account: the first one, or a rescue

`cucumber_admin` (U0.5 design §9) adds the first Admin after U0.5's first
release, and gets an Admin back in when nobody can log in: a forgotten
password, a lock, or a deactivated account. For an existing account it sets
the new password, reactivates it, lifts the lock and clears a pending
password change. It asks for the email, the name and the password (twice,
hidden), and asks before making someone an Admin who isn't one yet.

**The Owner types it** in the Terminal app on the Owner's Mac (it asks for a
password, and the auto-mode classifier blocks Claude on production). It runs
inside the running app container, as `cucumber_app`, like the app:

```bash
# staging
ssh -t cucumber-staging 'bash -lc "cd ~/cucumber/staging/src && export IMAGE_NAME=cucumber-staging CUCUMBER_VERSION=\$(cat ../current) && docker compose -p cucumber-staging --env-file ../secrets.env -f deploy/compose.server.yaml exec app python manage.py cucumber_admin"'
# production
ssh -t cucumber-server 'bash -lc "cd ~/cucumber/production/src && export IMAGE_NAME=cucumber-production CUCUMBER_VERSION=\$(cat ../current) && docker compose -p cucumber-production --env-file ../secrets.env -f deploy/compose.server.yaml exec app python manage.py cucumber_admin"'
```

Away from the home or lab network, use `cucumber-staging-remote` or
`cucumber-server-remote`. Use a different password on staging and
production, and save each in Bitwarden. First used on staging 2026-10-19
(U0.5 G5).

## Restore a copy (production)

As rehearsed on staging in [U0.4a G5](../roadmap/units/u0.4a-g5-verify.md#restore-steps-as-rehearsed),
with `production` in place of `staging`. Restore a copy into the version that
was running when it was taken (its file name says which deploy it came before).
Until U0.11 writes the full restore runbook, do this with Claude.

```bash
cd ~/cucumber/production/src          # its compose file matches the running version
export IMAGE_NAME=cucumber-production CUCUMBER_VERSION="$(cat ../current)"
dc() { docker compose -p cucumber-production --env-file ../secrets.env -f deploy/compose.server.yaml "$@"; }
copy=../backups/<the copy>.dump

dc stop app                                                      # 1. no writes during the restore
dc exec -T db pg_restore --list < "$copy" > /dev/null            # 2. the copy reads
dc exec -T db psql -U postgres -d postgres -c "DROP DATABASE cucumber WITH (FORCE)"   # 3.
dc exec -T db pg_restore -U postgres --create --exit-on-error -d postgres < "$copy"   # 4.
dc run --rm -T migrate python manage.py pending_migrations       # 5. expect {"pending": [], "unknown": []}
dc start app                                                     # 6.
# 7. /health/ says ok (step 6's first curl)
```

`--create` keeps the database's own settings ("only Cucumber's two roles may
connect"); `-T` keeps the copy from being corrupted on the way in. If step 5
lists `pending` migrations, deploy the version named in the copy's file name
first, then restore.
