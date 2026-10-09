# Phase 5 — Analytics & Monitoring

**Goal:** deck section *04* and SOP §8: metrics, availability, dashboards,
reports, GPS, sensors. All metrics are calculated from events — no extra
data entry (SOP §8).

**Release gate:** [R5](README.md#phase-release-gates)

---

### U5.1 · Metrics engine
- **Size:** L · **Deps:** U1.4, U1.5, U1.6
- **Source:** SOP §8 Metrics
- **Scope:** multiplication factor per SKU per cycle; contamination rate by SKU /
  media / staff / week; media effectiveness; days in stage; stage conversion;
  weeks-to-saleable; weekly lab output.
- **Acceptance:** reproduces the V.2 baselines (`PHL001` 5 → 55 in ~4 weeks,
  `PHL003` 8 → 66 in ~3 weeks) from migrated data.
- **Gate focus:** G2 each formula tested against a hand-calculated fixture ·
  G4 query performance review.

### U5.2 · Availability calculation
- **Size:** S · **Deps:** U1.2, U1.4 · **Decisions:** T-2, D-06
- **Source:** SOP §8 Availability, principle 6
- **Scope:** `available_to_sell = Portfolio AND live_count ≥ min_saleable_qty AND stage ≥ P4`.
  Never typed.
- **Acceptance:** no input field for availability anywhere; changes as soon as the
  underlying events change.
- **Gate focus:** G2 truth-table test of the three conditions.

### U5.3 · Dashboard & charts
- **Size:** M · **Deps:** U5.1, U5.2
- **Source:** deck 04 "Dashboard & Analytics"
- **Scope:** culture stage distribution; 12+ charts (contamination, loss,
  velocity, output…); filters by date / SKU / staff.
- **Acceptance:** every chart number traceable to a metric in U5.1; readable in
  light and dark mode and on phone.
- **Gate focus:** G5 Owner checks 3 numbers against manual counts.

### U5.4 · Report builder & export
- **Size:** L · **Deps:** U5.1
- **Source:** deck 04 "Report Builder"; deck "PDF exports"
- **Scope:** custom reports across lines, plants, media, inventory, tasks, audit
  logs; save report definitions; export PDF and CSV.
- **Acceptance:** reports respect permissions (no Zoho refs for non-Owner);
  large exports don't time out.
- **Gate focus:** G4 permission review on report queries.

### U5.5 · GPS mapping
- **Size:** S · **Deps:** U1.1
- **Source:** deck 01 / 04 "GPS"
- **Scope:** store collection GPS coordinates on plants; "Open in Maps" link.
- **Acceptance:** coordinates validated (lat −90..90, lon −180..180); link opens
  the phone's map app.
- **Gate focus:** G4 location data visible only to permitted roles.

### U5.6 · Environmental telemetry (UbiBot)
- **Size:** M · **Deps:** U3.1 · **Decisions:** D-09
- **Source:** deck 04 "Environmental Telemetry"
- **Scope:** pull temperature, humidity, light per growth room; charts; out-of-range alerts.
- **Acceptance:** API failures logged and shown as "data stale", never silently
  ignored; API key stored as a secret.
- **Gate focus:** G4 security review (external API, secret) · G5 one week of live readings.
