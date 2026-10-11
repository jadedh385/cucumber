# U0.1 UI-kit spike (throwaway)

Compares **daisyUI** and **Basecoat** on the same tiny screen so the Owner can
pick a UI kit on real phones (ADR-0001, U0.1 G1). This is **not** Cucumber's
code: it is deleted or archived once the kit is chosen.

What it proves:

- Login and logout (Django's built-in accounts).
- One data-entry screen, saved with HTMX, usable one-handed on a phone.
- A saved entry **can't be changed or deleted**, even with raw SQL
  (a database trigger; see `entries/migrations/0002_append_only_trigger.py`).
- A dropped connection shows "Not saved…" and keeps what was typed.

## Run it

```bash
cd spike
docker compose up -d --wait        # local PostgreSQL on port 5433
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser   # or ask Claude for the test login
uv run python manage.py runserver 0.0.0.0:8000
uv run pytest                      # 18 tests
```

Open `http://<this Mac's Wi-Fi address>:8000` on a phone **on the same
Wi-Fi**. Find the address with `ipconfig getifaddr en0`.

## Comparing on a phone

Do the same things in **A · daisyUI** and **B · Basecoat**, holding the phone
in one hand, and score each 1–5:

| Check | daisyUI | Basecoat |
|---|:-:|:-:|
| Easy to read in lab lighting | | |
| Easy to tap fields and Save with one thumb | | |
| Date picker and number keypad feel natural | | |
| Error messages are clear (try quantity 0, a date 8+ days back) | | |
| Looks professional / pleasant to use every day | | |
| **Total** | | |

Test on at least one **iPhone** and one **Android** phone.
