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
Admin role and a password with `dc run --rm migrate python manage.py
cucumber_admin` (U0.5 design §9; no `-T`: it asks questions).

## 1. Draft (Claude)

```bash
gh workflow run "Draft release" --ref main
gh run watch "$(gh run list --workflow "Draft release" --limit 1 --json databaseId --jq '.[0].databaseId')"
gh release list --limit 3                     # the new draft and its version, e.g. 2026.10.1
```

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

## 4. Deploy to production (Claude)

```bash
ssh -t cucumber-server
cd ~/cucumber/tools && git pull
uv run --no-dev python -m scripts.deploy production <version>
```

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
first if wanted: `--group Owner`) and try it, as the G6 line says.

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
