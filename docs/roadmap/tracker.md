# Unit × Gate Tracker

Mark each cell with the sign-off date (e.g. `10-14`) when the gate passes.
`·` = not started · `▶` = in progress · `✗` = failed (see gate log) · `—` = Won't Do.

**Gates:** G0 Spec · G1 Design · G2 Tests First · G3 Build · G4 Review · G5 Verify · G6 Release — see [gates.md](gates.md).

## Phase 0 — Foundations

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U0.1 | Decisions & stack | M | D-01, D-10, D-17 | 10-11 | 10-11 | 10-11 | 10-11 | 10-11 | ▶ | · |
| U0.2a | Domain model: schema | M | D-02, D-05, D-07, D-15; U0.3 | 10-11 | 10-11 | · | · | · | · | · |
| U0.2b | Domain model: event core services | M | U0.2a | 10-11 | 10-11 | · | · | · | · | · |
| U0.3 | Repo, CI, test harness | M | | ▶ | · | · | · | · | · | · |
| U0.4 | Environments & deploy | M | D-10 | · | · | · | · | · | · | · |
| U0.5 | Authentication | M | | · | · | · | · | · | · | · |
| U0.6 | Roles & permissions | M | D-03 | · | · | · | · | · | · | · |
| U0.7 | Audit trail & append-only store | M | D-07 | · | · | · | · | · | · | · |
| U0.8 | ID sequence service | S | | · | · | · | · | · | · | · |
| U0.9 | Reference lists | S | | · | · | · | · | · | · | · |
| U0.10 | App shell & UI kit | M | | · | · | · | · | · | · | · |
| U0.11 | Backup & restore baseline | S | | · | · | · | · | · | · | · |
| **R0** | **Platform ready** | | | | | | | | | · |

## Phase 1 — Core inventory (MVP)

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U1.1 | Plant registry | M | | · | · | · | · | · | · | · |
| U1.2 | Status & SKU promotion | S | T-1 | · | · | · | · | · | · | · |
| U1.3 | Batches | M | D-02, D-15 | · | · | · | · | · | · | · |
| U1.4 | Events & live counts | L | | · | · | · | · | · | · | · |
| U1.5 | Subculture & branching | M | | · | · | · | · | · | · | · |
| U1.6 | Stage change & transfer | M | | · | · | · | · | · | · | · |
| U1.7 | Collection counts | S | T-3, D-15, D-17 | · | · | · | · | · | · | · |
| U1.8 | Review queue & corrections | M | | · | · | · | · | · | · | · |
| U1.9 | Zoho reference link | S | T-4 | · | · | · | · | · | · | · |
| U1.10 | V.2 data migration | L | T-1, T-5 | · | · | · | · | · | · | · |
| **R1** | **MVP go-live** | | D-10 | | | | | | | · |

## Phase 2 — Lab depth

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U2.1 | Culture line view | M | | · | · | · | · | · | · | · |
| U2.2 | Subculture due alerts | S | D-11 | · | · | · | · | · | · | · |
| U2.3 | Lineage tree viewer | M | | · | · | · | · | · | · | · |
| U2.4 | Photos & attachments | M | | · | · | · | · | · | · | · |
| U2.5 | Acclimatization | M | D-06 | · | · | · | · | · | · | · |
| U2.6 | ~~Vessel tracking~~ **Won't Do** (D-02) | L | | — | — | — | — | — | — | — |
| **R2** | **Lab depth** | | | | | | | | | · |

## Phase 3 — Media, materials & locations

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U3.1 | Storage location hierarchy | M | | · | · | · | · | · | · | · |
| U3.2 | Zoho vendor copy (read-only) | S | | · | · | · | · | · | · | · |
| U3.3 | Materials & chemical lots | L | | · | · | · | · | · | · | · |
| U3.4 | Media formulation templates | M | | · | · | · | · | · | · | · |
| U3.5 | Media batch preparation | L | D-12 | · | · | · | · | · | · | · |
| **R3** | **Media & materials** | | | | | | | | | · |

## Phase 4 — Workflow & documentation

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U4.1 | Tasks & calendar | M | | · | · | · | · | · | · | · |
| U4.2 | Auto subculture tasks | S | D-11 | · | · | · | · | · | · | · |
| U4.3 | Protocol definitions | M | | · | · | · | · | · | · | · |
| U4.4 | Protocol execution runner | L | | · | · | · | · | · | · | · |
| U4.5 | QR label printing | M | | · | · | · | · | · | · | · |
| U4.6 | QR scanning & lookup | M | | · | · | · | · | · | · | · |
| U4.7 | Document management | M | | · | · | · | · | · | · | · |
| U4.8 | Culture label workflow | M | D-18 | · | · | · | · | · | · | · |
| **R4** | **Workflow** | | | | | | | | | · |

## Phase 5 — Analytics & monitoring

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U5.1 | Metrics engine | L | | · | · | · | · | · | · | · |
| U5.2 | Availability calculation | S | T-2, D-06 | · | · | · | · | · | · | · |
| U5.3 | Dashboard & charts | M | | · | · | · | · | · | · | · |
| U5.4 | Report builder & export | L | | · | · | · | · | · | · | · |
| U5.5 | GPS mapping | S | | · | · | · | · | · | · | · |
| U5.6 | Environmental telemetry | M | D-09 | · | · | · | · | · | · | · |
| **R5** | **Analytics** | | | | | | | | | · |

## Phase 6 — Infrastructure & security

| Unit | Name | Size | Blocked by | G0 | G1 | G2 | G3 | G4 | G5 | G6 |
|---|---|:-:|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| U6.1 | TOTP 2FA & recovery codes | M | | · | · | · | · | · | · | · |
| U6.2 | Encrypted backups & restore | M | | · | · | · | · | · | · | · |
| U6.3 | Universal CSV export | S | | · | · | · | · | · | · | · |
| U6.4 | Customization | M | | · | · | · | · | · | · | · |
| U6.5 | Sandbox mode | M | | · | · | · | · | · | · | · |
| U6.6 | Operational hardening | M | | · | · | · | · | · | · | · |
| **R6** | **Hardening** | | | | | | | | | · |

## Gate log

Record every failed gate and every sign-off with notes.

| Date | Unit / Gate | Result | Notes / sent back to | Signed by |
|---|---|---|---|---|
| 2026-10-11 | U0.2 / G0 | Passed | Spec signed off; Q1–Q8 answered; D-05 Resolved. Size L confirmed, not split | Jade |
| 2026-10-11 | U0.2 / G1 | Owner approved | Design note approved; G1 passes after the architect review | Jade |
| 2026-10-11 | U0.2 / G1 | Fixes required | Architect review: pass with fixes (H1–H5, M1–M6). Split into U0.2a / U0.2b; the count wins; record both who did and who saved an event | Jade |
| 2026-10-11 | U0.2a, U0.2b / G1 | Passed | Architect re-check: all required fixes done (H1–H5, M1–M7, N1–N6, N8). N7 settled the same day: Supervisors may enter another person's work, Techs may not | Jade |
| 2026-10-11 | U0.1 / G1 | Passed | Two UI kits compared with a spike each (daisyUI vs Basecoat); daisyUI chosen. Hosting: self-hosted MacBook Air, VPS fallback. G5: spike on the self-hosted machine, checked on an Android phone | Jade |
| 2026-10-11 | U0.1 / G2, G3 | Passed (recorded late) | Spike tests written first and seen failing, then 18 green; local runs (no CI yet, U0.3) | Claude |
| 2026-10-11 | U0.1 / G4 | Passed with notes | Spike code review: no CRITICAL; HIGH H1–H3 and MEDIUM M1–M6 are carry-forward notes, logged in U0.2 design (date tests), U0.3 AC12 (DEBUG off by default), U0.5 and U0.10. Spike not polished further: it is throwaway | Reviewer (code-reviewer agent) |
| 2026-10-11 | U0.1 / G5 | In progress | Spike runs on the self-hosted MacBook; iPhone 13 and Android (vivo Y3s) pass after a double-tap fix (issue #4); restart test passed. Left: check behind Cloudflare Tunnel + Access, waits for the domain | Jade |
| 2026-10-11 | U0.1 / G0 | Passed | D-01, D-10, D-17 Resolved; hosting (Singapore VPS) and file storage (local disk) decided; D-18 concept recorded, details at U4.8 G0. G1 = VPS provider + UI kit spike | Jade |
