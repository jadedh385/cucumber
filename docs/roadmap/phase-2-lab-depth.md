# Phase 2 — Lab Depth

**Goal:** the rest of deck section *01 Core Lab Management*: culture line views,
lineage trees, photos, acclimatization.

**Release gate:** [R2](README.md#phase-release-gates)

---

### U2.1 · Culture line view & contamination log
- **Size:** M · **Deps:** U1.5, U1.6
- **Source:** deck 01 "Tissue Culture Lines"
- **Scope:** per-line timeline from initiation (P0) to rooting; contamination
  history; current batches and counts; vessel health as batch-level notes (per D-02).
- **Acceptance:** timeline built only from events (nothing extra typed).
- **Gate focus:** G5 Owner compares 3 real lines against lab notes.

### U2.2 · Subculture due alerts
- **Size:** S · **Deps:** U2.1 · **Decisions:** D-11
- **Source:** deck 01 "subculture alerts"
- **Scope:** due / overdue flag per batch, using the D-11 interval rule; list on home screen.
- **Acceptance:** batch becomes due exactly at interval; subculture clears the flag.
- **Gate focus:** G2 time-travel tests (fixed clock).

### U2.3 · Lineage tree viewer
- **Size:** M · **Deps:** U1.5
- **Source:** deck 01 "Lineage Trees"; SOP principle 4
- **Scope:** interactive tree from `parent_batch_id`; stage color coding; pan and
  zoom; tap a node to open the batch.
- **Acceptance:** renders a 500-node tree smoothly; usable on phone; color is not the
  only stage cue (label too).
- **Gate focus:** G1 library choice · G5 accessibility check.

### U2.4 · Photos & attachments
- **Size:** M · **Deps:** U1.1
- **Source:** deck 01 "photos"
- **Scope:** shared file storage service; photos on plants and batches; camera
  capture on phone; thumbnails. Reused by U4.7.
- **Acceptance:** file type and size validated; images stripped of GPS EXIF unless
  the user opts in; files included in backups.
- **Gate focus:** G4 **security review** (uploads, path traversal).

### U2.5 · Acclimatization
- **Size:** M · **Deps:** U1.6 · **Decisions:** D-06
- **Source:** deck 01 "Acclimatization"
- **Scope:** hardening-off batches, tray checks (alive / lost), survival rate,
  transfer to greenhouse / nursery.
- **Acceptance:** survival rate calculated from events; transfer conserves units.
- **Gate focus:** G5 a real tray tracked for one full cycle.

### U2.7 · Needs attention list
- **Size:** M · **Deps:** U2.1, U2.2, U0.10 · **Decisions:** D-27
- **Source:** Owner request (2026-10-13)
- **Scope:** one "Needs attention" list on the home screen that gathers every
  reason a batch or task needs someone: subculture due / overdue (U2.2),
  Collection count overdue (U1.7), entries waiting for review (U1.8), and new
  rules: in quarantine too long, contamination above a set rate, no event in
  X days. Each item says why it is listed and opens the batch. Thresholds are
  settings the Owner can change (D-27).
- **Acceptance:** each rule lists a batch exactly when its threshold is
  crossed and drops it once the reason is cleared; the list is built only from
  events and settings (nothing extra typed); usable on phone.
- **Gate focus:** G2 time-travel tests (fixed clock) for every rule · G5 Owner
  compares a week of the list against the lab.

### U2.8 · Discord attention alerts
- **Size:** M · **Deps:** U2.7, U0.4a, U0.6 · **Decisions:** D-27
- **Source:** Owner request (2026-10-13)
- **Scope:** post the "Needs attention" items to Discord (e.g. a daily summary:
  "5 batches due for subculture today") with a link into Cucumber. **Controls**
  for the Owner: switch the whole feature, or each alert type, on or off;
  choose the channel and the time of the summary; mute for a period. Messages
  carry batch codes and counts only, with mentions off; the link still needs
  the Access email check and Cucumber login. Runs on a schedule (the scheduler
  is chosen at G1).
- **Acceptance:** a summary is sent once per scheduled time, never twice; a
  switched-off or muted type sends nothing; if Discord fails, Cucumber keeps
  working and the failure is logged and shown to the Owner; only the Owner
  can change the controls.
- **Gate focus:** G2 no-duplicate and on/off tests · G4 **security review**
  (webhook secret, what a message may contain) · G5 Owner and staff use it for
  one week.

### U2.6 · Vessel tracking — **Won't Do**
- **Size:** L · **Deps:** U1.3 · **Decisions:** D-02
- **Status:** closed. D-02 chose batch-only tracking; contamination is handled by
  splitting contaminated vessels into a quarantined child batch (U1.5 / U2.1).
