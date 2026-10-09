# Phase 6 — Infrastructure, Security & Productization

**Goal:** deck section *05*: 2FA, encrypted backups, exports, customization,
sandbox, operational hardening.
If D-10 says the app is on the public internet, **U6.1 and U6.6 move into R1**.

**Release gate:** [R6](README.md#phase-release-gates)

---

### U6.1 · TOTP 2FA & recovery codes
- **Size:** M · **Deps:** U0.5
- **Source:** deck 05 "Role Access Control"
- **Scope:** authenticator-app 2FA; one-time recovery codes; Owner can require
  2FA for all; Owner can reset a user's 2FA.
- **Acceptance:** recovery codes single-use and stored hashed; 2FA required at
  login when enrolled.
- **Gate focus:** G4 **security review mandatory**.

### U6.2 · Encrypted backups & full restore
- **Size:** M · **Deps:** U0.11
- **Source:** deck 05 "Encrypted Backups"
- **Scope:** AES-256-GCM encryption of backups; key management outside the
  backup location; full DB + files restore.
- **Acceptance:** backup unreadable without the key; tampered backup fails
  integrity check; restore drill passes.
- **Gate focus:** G4 crypto review · G5 timed restore drill.

### U6.3 · Universal CSV export
- **Size:** S · **Deps:** all data units at G6
- **Source:** deck 05 "universal CSV exports"
- **Scope:** export every table to CSV (Owner only); respects field-level permissions.
- **Acceptance:** CSV opens cleanly in Sheets / Excel (UTF-8, Thai text intact);
  formula injection neutralized.
- **Gate focus:** G4 CSV injection test.

### U6.4 · Customization
- **Size:** M · **Deps:** U0.9, U0.10
- **Source:** deck 05 "Customization"
- **Scope:** configurable pick lists, lab terminology labels, timezone, date
  format, temperature unit.
- **Acceptance:** stored data stays canonical (UTC, °C); only display changes.
- **Gate focus:** G2 week-number tests across timezones.

### U6.5 · Sandbox mode
- **Size:** M · **Deps:** U0.4, U6.3
- **Source:** deck 05 "Sandbox Mode"
- **Scope:** separate sandbox workspace with sample data for training; clearly
  marked in the UI; one-click reset.
- **Acceptance:** sandbox actions can never touch live data (separate DB / schema).
- **Gate focus:** G2 isolation test · G5 new staff trained only in sandbox.

### U6.6 · Operational hardening
- **Size:** M · **Deps:** U0.4
- **Scope:** rate limiting on all endpoints; error monitoring; uptime check;
  log retention; dependency vulnerability scan in CI.
- **Acceptance:** brute-force login blocked; alerts reach the Owner; no sensitive
  data in logs or error messages.
- **Gate focus:** G4 security review against the full security checklist.
