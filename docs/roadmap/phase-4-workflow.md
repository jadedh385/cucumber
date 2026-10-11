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
- **Note:** printing approach shared with U4.8; see [label concept](#label-concept-d-18) (D-18).

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
  Printing approach shared with U4.5 (see below).
- **Acceptance:** saving a subculture that makes 30 jars queues 30 labels
  without retyping; a quarantine split queues labels for the moved jars; a
  reprint without a reason is refused.
- **Gate focus:** G5 print test on the actual printer, at lab volume.
- **Placement:** candidate to move into Phase 1 (MVP) so go-live doesn't keep
  hand-typed labels; decided with D-18.

#### Label concept (D-18)

Agreed 2026-10-11 as a concept only. Details are settled at U4.8 G0.

**How printing works.** Today the lab prints from a Bluetooth label printer
through its phone app. Cucumber does not connect to the printer.

1. **Print list (first version).** When an event creates jars, Cucumber shows
   the labels to print: how many, the exact text of each, and what the QR code
   holds. Staff print them from the printer's phone app and tick the set as
   printed.
2. **File export (if the printer app supports it).** Many Bluetooth label apps
   (e.g. NIIMBOT, Phomemo) can batch-print from an Excel / CSV file. Cucumber
   offers the print list as a download, so a 30-jar subculture is one import
   and nothing is retyped. Check this with the lab's actual printer app at G0.
3. **Direct printing (later, only if needed).** Safari on iPhone has no Web
   Bluetooth, so a web app can't reach a Bluetooth printer by itself. This
   would need a network printer, a small print program on a lab PC, or the
   printer vendor's toolkit. Revisit only if steps 1–2 are too slow.

**Draft label content** (confirm against today's labels at G0):

| On the label | Why |
|---|---|
| `BAT-nnnnn` + QR code holding only that ID | Identifies the jar's batch; scan for live details (U4.6) |
| Plant name, short form | Readable without a phone; format from D-19 |
| Stage code (e.g. `P2`) and media code | What the jar is and what it's on |
| Event date (intake / subculture date) | Age of the culture at a glance |
| Operator initials (optional) | Who did the work; decide at G0 |

Left off on purpose: anything that changes after printing (status, counts,
location), which the QR scan shows live instead. No prices or costs (SOP §2
principle 2).

**Label stock.** Labels must survive 70% ethanol wipes, growth-room humidity
and months under lights. Direct-thermal paper labels can fade or smudge.
Synthetic (polypropylene or polyester) labels are made for this. G5 test: print
on the chosen stock, wipe with ethanol, and leave in the growth room for one
subculture cycle.

**To collect at G0:** printer make / model and label size; a photo of today's
label; labels per week; who prints, where, and on which phone; whether the
printer app imports Excel / CSV.
