# Phase 4 — Workflow & Documentation

**Goal:** deck section *03*: tasks, protocol runner, QR labels, documents.
(The audit trail from deck 03 is already built in U0.7.)

**Release gate:** [R4](README.md#phase-release-gates)

---

### U4.1 · Tasks & calendar
- **Size:** M · **Deps:** U0.6, U0.10
- **Source:** deck 03 "Tasks & Scheduling"
- **Scope:** tasks with assignee, due date, link to a record; day / week / month
  calendar; team workload view.
- **Acceptance:** each user sees their tasks first; overdue highlighted.
- **Gate focus:** G5 one week of real lab tasks run in the app.

### U4.2 · Auto-generated subculture tasks
- **Size:** S · **Deps:** U4.1, U2.2 · **Decisions:** D-11
- **Source:** deck 03 "auto-generated subculture tasks"
- **Scope:** due alerts from U2.2 create tasks; doing the subculture closes the task.
- **Acceptance:** no duplicate tasks for the same batch and due date.
- **Gate focus:** G2 idempotency test.

### U4.3 · Protocol definitions
- **Size:** M · **Deps:** U0.9, U3.4 · **Decisions:** D-08
- **Source:** deck 03; Cucumber's own design (the *Protocol Tracking System
  Plan V.1* is shelved, D-08)
- **Scope:** versioned protocols: ordered steps, data fields per step, wait
  timers, which steps need verification.
- **Acceptance:** uses Cucumber's stage and media lists (U0.9); editing creates a new version.
- **Gate focus:** G0 short design note for the protocol model, reviewed by the Owner.

### U4.4 · Protocol execution runner
- **Size:** L · **Deps:** U4.3, U1.4
- **Source:** deck 03 "Protocol Execution Runner"
- **Scope:** run a protocol step by step; capture data; wait timers with
  notification; second-person verification on flagged steps; run can write
  inventory events (e.g. subculture) at the end.
- **Acceptance:** a verifier can't be the same user as the performer; an
  interrupted run resumes; completed runs are read-only.
- **Gate focus:** G2 verifier ≠ performer test · G5 a real P0 sterilization run.

### U4.5 · QR label printing
- **Size:** M · **Deps:** U0.8, U1.3, U3.3
- **Source:** deck 03 "QR Code Labels"
- **Scope:** labels for batches, plants, media lots, chemical lots; custom label
  sizes; print sheet / single label.
- **Acceptance:** QR encodes a record ID, not personal or secret data; prints
  correctly on the lab's label printer.
- **Gate focus:** G5 print test on the actual printer.
- **Note:** printer integration is shared with [U4.8](#u48--culture-label-workflow) (D-18).

### U4.6 · QR scanning & lookup
- **Size:** M · **Deps:** U4.5
- **Source:** deck 03 "Mobile QR scanning"
- **Scope:** phone camera scan → opens the record → quick actions (log event,
  subculture).
- **Acceptance:** scan-to-record in under 2 s; unknown code shows a clear message;
  permissions still apply after the scan.
- **Gate focus:** G5 scanning in real lab lighting.

### U4.7 · Document management
- **Size:** M · **Deps:** U2.4, U3.3
- **Source:** deck 03 "Document Management"
- **Scope:** upload SDS sheets, certificates, reference docs; categories; search;
  inline preview; link a doc to a material or plant.
- **Acceptance:** file type / size validated; preview works for PDF and images.
- **Gate focus:** G4 security review (uploads).

### U4.8 · Culture label workflow
- **Size:** M · **Deps:** U0.8, U1.3, U1.5 · **Decisions:** D-18
- **Source:** Owner request 2026-10-10 (labels were printed one by one, typed by hand)
- **Scope:** events create the print list: an intake, subculture, quarantine or
  transfer queues one label per jar for the batch. Print a whole set in one
  action; reprint with a reason; "unprinted labels" list; label usage and waste
  per week (quantities only, no cost, SOP §2 principle 2). A label identifies its
  batch by `BAT-nnnnn` (and QR); other text is printed as it was at print time.
  Printer integration is shared with U4.5.
- **Acceptance:** saving a subculture that makes 30 jars queues 30 labels
  without retyping; a quarantine split queues labels for the moved jars; a
  reprint without a reason is refused.
- **Gate focus:** G5 print test on the actual printer, at lab volume.
- **Placement:** candidate to move into Phase 1 (MVP) so go-live doesn't keep
  hand-typed labels; decided with D-18.
