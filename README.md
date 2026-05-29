# AuspexAI Researcher Dashboard

Tenant-scoped researcher / tenant view for [AuspexAI](https://github.com/auspexai) — a volunteer-driven, open-source distributed compute network for AI safety research.

## Status

**R-D0 — scaffold (2026-05-28).** FastAPI backend + SvelteKit static frontend; `auspexai-dashboard serve` runs the dashboard locally and opens a browser. Placeholder pages + a health probe (coordinator connectivity + tenant-key presence). No authenticated coordinator calls yet. Full design + milestones: `Documentation/AuspexAI/v0.1.0/researcher_dashboard_design.md`.

The researcher dashboard is one of four Phase 1 UI surfaces per §5.18 of the AuspexAI Principles & Scope document.

### Run it locally

```bash
cd backend && pip install -e ".[dev]"
cd ../frontend && pnpm install && pnpm build && cp -r build/* ../backend/src/auspexai_researcher_dashboard/static/
auspexai-dashboard serve        # starts on 127.0.0.1:4228 and opens a browser
```

For frontend dev with live reload: `cd frontend && pnpm dev` (proxies `/api` to the backend on :4228).

### Milestones

- **R-D0** ✅ scaffold (this).
- **R-D1** prerequisites in sibling repos: RFC 9421 request signer in `tenant-sdk`; tenant-scoped `GET /experiments/{id}/receipts` on `platform`.
- **R-D2** my-experiments list + detail with work-unit/replication progress (signed reads).
- **R-D3** my-experiment receipts view.
- **R-D4** lifecycle actions (abort; pause/resume).
- **R-D5 (v1)** live SSE progress; receipt-detail verification; create-experiment form.

## Scope

The researcher dashboard is the **tenant-scoped** view for researchers who ship experiments on AuspexAI: see and manage your own experiments, work units, receipts, and contributors. Each researcher sees only their own tenant's data; cross-tenant queries are rejected at the coordinator. Sibling Phase 1 UI surfaces — operator console, tenant onboarding form, public receipt verifier — are separate codebases per §5.18.

### Phase 1 v0

- My experiments list + detail
- My experiment work-unit progress + replication state
- My receipts list (for my experiments)
- Lifecycle actions (abort experiment)

### Phase 1 v1

- Live SSE for my experiment progress
- Receipt detail with COSE + in-toto + Rekor verification

## Stack

- **Frontend:** SvelteKit + TypeScript (matches operator console per §5.18)
- **Backend:** FastAPI (Python) — colocated with the frontend. Speaks to the coordinator via HTTP Message Signature (RFC 9421) using the researcher's existing maintainer Ed25519 keypair from the [tenant SDK](https://github.com/auspexai/tenant-sdk).
- **Auth:** researcher HTTP Message Signature (RFC 9421) per §5.18

## License

[Apache-2.0](LICENSE) — matches the [tenant SDK](https://github.com/auspexai/tenant-sdk) per the Q16 SDK boundary precedent. The researcher dashboard consumes the coordinator's published HTTP API contract; it is not a platform internal.

## Governance & policies

- [Governance](https://github.com/auspexai/.github/blob/main/GOVERNANCE.md) — roles, decision rules, recruitment, conflict of interest
- [Code of Conduct](https://github.com/auspexai/.github/blob/main/CODE_OF_CONDUCT.md) — community standards, reporting, escalation pathway
- [Contributing](https://github.com/auspexai/.github/blob/main/CONTRIBUTING.md) — DCO sign-off, PR workflow, RFC requirement for substantial architectural changes
- [Research Ethics Policy](https://github.com/auspexai/.github/blob/main/RESEARCH_ETHICS_POLICY.md) — what AI safety research can run on the network and how it's reviewed

## Watch this repo

Activity begins as the coordinator daemon comes online. Issues and discussion welcome.
