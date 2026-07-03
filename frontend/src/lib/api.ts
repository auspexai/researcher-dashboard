// Shared client for the local dashboard backend (researcher_dashboard_design.md §5).
//
// The backend (api.py) proxies tenant-scoped reads to the coordinator, signing
// each request with the researcher's SDK key, and on failure returns a stable
// envelope: {error: {kind, message, coordinator_status}}. We surface that as a
// typed ApiError so pages can branch on `kind` — in particular the
// "key not recognized" (unbound / rotated) case (§10 Q4).

export type ErrorKind =
	| 'no_identity'
	| 'unauthorized'
	| 'not_found'
	| 'conflict'
	| 'not_ready'
	| 'unreachable'
	| 'coordinator_error'
	| 'client_error'
	// Local-operations (§8): the dashboard's own machine, not the coordinator.
	| 'unconfigured'
	| 'bad_request'
	| 'render_failed';

export class ApiError extends Error {
	kind: ErrorKind;
	coordinatorStatus: number | null;

	constructor(kind: ErrorKind, message: string, coordinatorStatus: number | null = null) {
		super(message);
		this.name = 'ApiError';
		this.kind = kind;
		this.coordinatorStatus = coordinatorStatus;
	}
}

async function request<T>(path: string, method: 'GET' | 'POST', payload?: unknown): Promise<T> {
	let resp: Response;
	try {
		resp = await fetch(
			path,
			payload === undefined
				? { method }
				: {
						method,
						headers: { 'Content-Type': 'application/json' },
						body: JSON.stringify(payload)
					}
		);
	} catch (e) {
		throw new ApiError('unreachable', `could not reach the local dashboard backend: ${e}`);
	}
	let body: unknown = null;
	try {
		body = await resp.json();
	} catch {
		/* non-JSON body — leave null */
	}
	if (!resp.ok) {
		const err = (body as { error?: { kind?: ErrorKind; message?: string; coordinator_status?: number | null } } | null)?.error;
		if (err?.kind) {
			throw new ApiError(err.kind, err.message ?? 'request failed', err.coordinator_status ?? null);
		}
		throw new ApiError('client_error', `request failed (HTTP ${resp.status})`);
	}
	return body as T;
}

const getJson = <T>(path: string): Promise<T> => request<T>(path, 'GET');
// Lifecycle actions (R-D4): bodyless POSTs. A `conflict`-kind ApiError carries
// the coordinator's own reason (e.g. "experiment is already completed").
const postJson = <T>(path: string): Promise<T> => request<T>(path, 'POST');
// Demand-board submits (R-D6): POSTs WITH a JSON body, forwarded verbatim to
// the coordinator (which validates the shape and owns authorization).
const postJsonBody = <T>(path: string, payload: unknown): Promise<T> =>
	request<T>(path, 'POST', payload);

export type ExperimentStatus =
	| 'submitted'
	| 'approved'
	| 'running'
	| 'paused'
	| 'completed'
	| 'aborted'
	| 'archived'
	| (string & {});

// Mirrors the coordinator's tenant-scoped ExperimentResponse — the fields an
// owning researcher sees (operator-only fields like max_units never arrive).
export interface Experiment {
	experiment_id: string;
	tenant_id?: string;
	status?: ExperimentStatus;
	// E15: coarse, presentation-only phase (queued/running/inert/awaiting_assessment/…)
	// so `status` doesn't conflate the in-flight states. None where status says it.
	run_phase?: string;
	tenant_experiment_label?: string;
	submitted_at?: string;
	started_at?: string;
	completed_at?: string;
	submissions_finalized?: boolean;
	last_action_at?: string;
	last_action_by_class?: string;
	manifest_hash?: string;
	revision?: number;
	integrity_policy?: string;
	max_unit_duration_seconds?: number;
	// M-Results retention state (tenant-scoped).
	retention_hold?: boolean;
	results_collected_at?: string;
	// §9 #48 admission-assessment provenance (tenant-scoped; the researcher sees
	// its OWN verdict). Drives the lifecycle timeline. assessed_by is operator-
	// only so it never arrives here.
	research_class?: string | null;
	assessment_decision?: 'auto' | 'review' | string | null;
	assessment_tier?: number | null;
	assessment_rationale?: string | null;
	assessment_envelope?: { name: string; passed: boolean; detail: string }[] | null;
	assessed_at?: string | null;
}

export interface WorkUnits {
	work_units?: unknown[];
	counts_by_status?: Record<string, number>;
}

// Mirrors the coordinator's tenant-scoped ReceiptSummary (R-D1b). Worker
// identity (worker_id / worker_pubkey) is stripped coordinator-side, so the
// tenant sees that a receipt exists for its experiment, not who earned it.
export interface Receipt {
	receipt_id: string;
	experiment_id?: string;
	issued_at?: string;
}

// One of the tenant's OWN-account workers, shown non-anonymously (R-D3
// own-worker enrichment). Only present for workers bound to the same account as
// the experiment's tenant; the coordinator strips third-party identities and
// only sends this to the owning researcher (ACCOUNT_SCOPED).
// Derived worker status — the coordinator collapses retired/quarantined/
// heartbeat-recency into one label (retired > quarantined > offline > active).
export type WorkerStatus = 'active' | 'offline' | 'quarantined' | 'retired';

export interface OwnWorkerActivity {
	worker_id: string;
	worker_pubkey_hex: string;
	result_count: number;
	trust_tier: number;
	last_activity_at?: string;
	// Account-scoped: present only on your own-account workers. `quarantine_reason`
	// is the maintainer's reason and is non-null only when status is 'quarantined'.
	status?: WorkerStatus;
	quarantine_reason?: string | null;
	last_heartbeat_at?: string;
	// R-D #2: this worker's role for THIS experiment — so an account worker that
	// can't serve it shows with a reason instead of vanishing from the list.
	experiment_eligibility?: 'backing' | 'eligible' | 'ineligible';
	experiment_ineligible_reason?: string | null;
}

// Mirrors the coordinator's ExperimentActivityResponse (R-D3). The aggregate
// fields carry no per-worker identity; `own_workers` is the one account-scoped
// exception — the tenant's own-account workers, absent when the tenant isn't
// account-linked.
export interface ExperimentActivity {
	experiment_id?: string;
	active_contributor_count?: number;
	total_work_units?: number;
	work_unit_counts?: Record<string, number>;
	last_activity_at?: string;
	completions_total?: number;
	replication_target_total?: number;
	// Public, identity-free: total workers active network-wide (heartbeat-fresh,
	// not retired/quarantined) — the size of the collective backing the network.
	network_active_workers?: number;
	own_workers?: OwnWorkerActivity[];
	// D8 "liveness note": a plain-language explanation of the run's current state
	// (TENANT_SCOPED). Notably, a C14 regime-3 pause self-explains as a "waiting
	// for an eligible worker, auto-resumes" hold rather than a silent stall.
	// Absent when there's nothing to explain (the healthy case).
	liveness_note?: string;
	// Richer D8 (live corroboration health): completed units whose independent
	// replicas DIVERGED — workers disagreed, so no agreement and no receipt. A
	// live > 0 is the nondeterminism / model-version-skew signal (NOT model
	// drift), surfaced here instead of only retrospectively in the evidence
	// footprint. PUBLIC: an aggregate count, no per-worker identity. Absent on the
	// empty rollup (no work units submitted yet).
	diverged_unit_count?: number;
	// D12 run phase: a derived, presentation-only refinement of the overloaded
	// 'approved' status — 'queued' (approved but nothing in flight yet) vs
	// 'running' vs 'provisioning' vs 'paused'. Lets the UI distinguish "in line"
	// from "in progress" without a new ExperimentStatus. Absent for terminal
	// states (the status string already says it). TENANT_SCOPED.
	run_phase?: 'queued' | 'running' | 'provisioning' | 'paused' | (string & {});
	// D12 queue position: 1-based rank + total depth among approved experiments in
	// the scheduler's registration order — "you're in line, here's where". Present
	// only while queued; bare integers, no other-tenant identities.
	queue_position?: number;
	queue_depth?: number;
	// D12 busy/idle: eligible-worker capacity. capable_worker_count = active
	// workers that can run this experiment; capable_busy_count = of those, how
	// many are currently busy on some run.
	capable_worker_count?: number;
	capable_busy_count?: number;
	// D12 5c: in-flight model-download progress for a queued experiment whose
	// required model a volunteer is pulling. pct is null until a total is known.
	download_progress?: {
		model_id?: string;
		bytes_downloaded?: number | null;
		total_bytes?: number | null;
		pct?: number | null;
	};
}

// One result in the delivery view (R-D5, coordinator M-Results). The science
// (payload + semantic_hash) is tenant-scoped; worker identity is stripped
// coordinator-side. An aged-off row omits `payload` and carries aged_off=true —
// the receipt + semantic_hash still prove the unit ran. In the evidence bundle
// (EB-1) each row also carries the worker's signature members: the pubkey is a
// pseudonymous verification handle, not an identity.
export interface ResultItem {
	result_id?: string;
	unit_id?: string;
	completed_at?: string;
	receipt_id?: string;
	is_consensus?: boolean;
	aged_off?: boolean;
	payload_aged_off_at?: string;
	semantic_hash?: string;
	payload?: Record<string, unknown>;
	worker_signature?: string;
	worker_pubkey_hex?: string;
	exit_code?: number;
	environment?: Record<string, unknown>;
	// C7 Inc 4: present on the consensus row of a within_cell_tolerance unit —
	// HOW the replicas agreed (persisted by the coordinator at issuance):
	// deterministic representative + per-feature spread vs the declared envelope.
	consensus_evidence?: {
		method?: string;
		representative?: Record<string, unknown>;
		representative_hash?: string;
		spread?: Record<string, number>;
		envelope?: Record<string, { rule?: string; rel?: number; abs?: number; min?: number }>;
		agreeing_workers?: number;
		outlier_count?: number;
	};
}

export interface ResultList {
	results?: ResultItem[];
	next_cursor?: string | null;
}

// The result-set attestation (coordinator GET .../attestation; integrity
// panel, R-D inc-1): a COSE-signed in-toto statement over the merkle root of
// the experiment's consensus set, plus its Rekor transparency-log anchor once
// the hourly sweep has anchored it. `partial` marks a mid-run checkpoint
// (consensus-so-far) rather than the final persisted attestation.
export interface Attestation {
	attestation_id?: string;
	experiment_id?: string;
	tenant_id?: string;
	merkle_root?: string;
	algorithm?: string;
	unit_count?: number;
	units?: { unit_id: string; consensus_result_hash?: string }[];
	cose_b64?: string;
	signing_key_pubkey_hex?: string;
	rekor_log_index?: number | null;
	rekor_entry_uuid?: string | null;
	rekor_inclusion_proof?: Record<string, unknown> | null;
	partial?: boolean;
	// Firewall #2: the coordinator-asserted, COSE-signed governance footprint —
	// the apparatus conditions behind this evidence, so a researcher can correct
	// for apparatus influence. Absent on pre-firewall attestations.
	governance_footprint?: GovernanceFootprint | null;
	diverged_units?: { unit_id: string; result_hashes?: string[] }[] | null;
}

// Citation / acknowledgment block for a completed experiment (System B, D). The PI
// is the producing tenant; named_contributors are the volunteers who opted into
// public attribution, everyone else is folded into anonymous_contributor_count.
export interface Citation {
	experiment_id?: string;
	tenant_id?: string;
	named_contributors?: string[];
	anonymous_contributor_count?: number;
	total_contributor_accounts?: number;
	acknowledgment?: string;
}

// Firewall #2 apparatus footprint (governance conditions on the evidence).
export interface GovernanceFootprint {
	schema_version?: number;
	tenant?: { tier?: string; identity_gate?: string };
	replication?: {
		integrity_policy?: string;
		replication_factor?: number;
		tier_floored?: boolean;
		sub_floor?: boolean;
	};
	approval?: {
		experiment?: string; // 'auto' | 'human'
		assessment?: { research_class?: string; tier?: number } | null;
		promotion?: { tier_set_by?: string | null };
	};
	independence?: {
		basis?: string;
		distinct_accounts?: number;
		distinct_workers?: number;
		distinct_served_models?: number;
	};
	integrity_basis?: { counts?: Record<string, number> };
	// §41 / A2: the containment the apparatus REQUIRED vs the sandbox policies the
	// consensus workers actually RAN UNDER — so a researcher can stratify by it.
	containment?: { required?: string; ran_under?: string[] };
	// v0.2 M1: the manifest-declared generation policy — greedy (byte-deterministic
	// decoding) vs seeded_sampling (declared temperature + pinned seed + whitelist
	// knobs). Divergence is interpretable only in kind: sampled replicas
	// legitimately differ; greedy replicas should not.
	generation?: {
		mode?: string; // 'greedy' | 'seeded_sampling'
		params?: Record<string, number | string>;
	};
}

// The Drift Benchmark report (ratified standard: peak + breadth headline;
// byte-divergence and within-run divergence are separate overlays, never
// folded into the scalar; the REFERENCE bundle's signed manifest defines the
// envelope, and published numbers always name their reference).
export interface BenchmarkFeature {
	feature: string;
	rule: string;
	eu: number | null;
	eu_max: number | null;
	pairs: number;
	invalid_excluded: number;
}
export interface BenchmarkProbe {
	key: string;
	peak_eu: number | null;
	beyond_envelope: boolean;
	byte_divergence_rate: number | null;
	observations: number;
	reference_observations: number;
	features: BenchmarkFeature[];
}
export interface BenchmarkReport {
	peak_eu: number | null;
	breadth: number | null;
	byte_divergence_rate: number | null;
	diverged_units_total: number | null;
	diverged_by_key: Record<string, number> | null;
	key_feature: string;
	notes: string[];
	probes: BenchmarkProbe[];
}
export interface BenchmarkRecord {
	schema: string;
	computed_at: string;
	observation: { experiment_id: string; label?: string | null };
	reference: { experiment_id: string; label?: string | null };
	report: BenchmarkReport;
	saved_path?: string | null;
}
export interface BenchmarkSummary {
	computed_at?: string;
	observation?: { experiment_id?: string; label?: string | null };
	reference?: { experiment_id?: string; label?: string | null };
	peak_eu?: number | null;
	breadth?: number | null;
	byte_divergence_rate?: number | null;
	diverged_units_total?: number | null;
	probes?: number;
	path?: string;
}

export interface VerificationCheck {
	name: string;
	state: 'pass' | 'fail' | 'na';
	detail?: string;
}

// The named-check result of the local verifier (auspexai-tenant verify_bundle),
// run by the dashboard backend on THIS machine when a bundle is collected.
export interface BundleVerification {
	ok: boolean;
	checks: VerificationCheck[];
	rekor: { state: 'anchored' | 'pending'; log_index?: number | string };
	error?: string;
}

export interface ExportResponse {
	bundle: ExportBundle;
	verification: BundleVerification;
	// Where the dashboard saved the verified bundle on disk (the shared
	// runs/<label>/bundle.json layout — same as the CLI). null if the disk
	// write was unavailable; the SPA falls back to a browser download.
	saved_path?: string | null;
}

// The evidence bundle (coordinator GET .../results/export; EB-1, §9 #47).
// Self-contained and offline-verifiable: consensus payloads + worker
// signatures + work-unit inputs + receipts + the manifest + the result-set
// attestation with its Rekor anchor + a coordinator-signed custody record.
// Collecting it transfers data custody to the researcher; for a COMPLETED
// experiment the custody record signs the attestation's merkle root
// (root_kind 'result-set/v1' — one root binds data ↔ custody ↔ Rekor).
export interface ExportBundle {
	schema?: string;
	experiment_id?: string;
	manifest_hash?: string;
	manifest?: Record<string, unknown> | null;
	work_units?: { unit_id: string; payload: Record<string, unknown> }[];
	consensus_results?: ResultItem[];
	receipts?: { receipt_id: string; cose_b64: string }[];
	attestation?: {
		attestation_id: string;
		merkle_root: string;
		algorithm: string;
		cose_b64: string;
		signing_key_pubkey_hex: string;
		rekor_log_index: number | null;
		rekor_entry_uuid: string | null;
		rekor_inclusion_proof: Record<string, unknown> | null;
	} | null;
	transfer?: {
		transfer_id: string;
		result_set_root: string;
		root_kind?: string;
		attestation_id?: string | null;
		collected_at: string;
		collected_by_pubkey: string;
		manifest_hash: string;
		receipt_count: number;
		coordinator_signature: string;
		coordinator_pubkey_hex: string;
	};
}

// The confirmed bound identity from the coordinator's /auth/whoami. For a
// researcher: credential_class="researcher" + their own tenant_id + pubkey_hex.
export interface WhoAmI {
	credential_class: string;
	tenant_id?: string;
	pubkey_hex?: string;
	// Account-scoped: present only when the caller's own account is suspended.
	// The coordinator surfaces both so the dashboard can explain the pause.
	suspended_at?: string;
	suspension_reason?: string | null;
	// D9 Phase 4 (D4): the researcher's own research-standing (0-3) + progress toward
	// the R2 review. Account-scoped — present for the account holder.
	research_standing?: number;
	research_standing_distinct?: number;
	research_standing_threshold?: number;
	research_standing_eligible_for_r2?: boolean;
	// D8: the linked ORCID iD (e.g. "0000-0002-1825-0097"), if any. Account-scoped.
	orcid_id?: string | null;
	// E11 D3a: whether identity verification is currently STAMPED (distinct from
	// "an iD is linked") — drives the Link vs Re-verify ORCID affordance.
	identity_verified?: boolean | null;
	// The account-identity root, account-scoped: `display_name` is the verified
	// handle (the GitHub login for a github root); `idp` is the provider. Lets the
	// Identity card render the GitHub identity beside ORCID.
	display_name?: string | null;
	idp?: 'github' | 'orcid' | string;
}

// One worker CURRENTLY bound to the researcher's account, with derived liveness
// for the Overview "Your workers" panel (GET /accounts/me/workers). Account-scoped:
// the coordinator only ever returns the caller's own-account workers. Distinct
// from OwnWorkerActivity (per-EXPERIMENT participation); this is account-level
// connectivity with no experiment role.
export interface AccountWorker {
	worker_id: string;
	pubkey_hex: string;
	trust_tier: number;
	status: WorkerStatus;
	quarantine_reason?: string | null;
	last_heartbeat_at?: string;
	result_count: number;
}

// ── Demand board (R-D6, §9 #46) ────────────────────────────────────────────

export interface CatalogEntry {
	model_id: string;
	worker_count: number;
}

export interface ModelRequest {
	request_id: string;
	model_id: string;
	hf_repo: string | null;
	reason: string;
	status: 'available' | 'pending' | 'fulfilled' | 'declined' | string;
	created_at: string;
	resolved_by: string | null;
	resolution_reason: string | null;
}

export interface Assessment {
	dependencies: string;
	security: string;
	alternatives: string;
	summary: string | null;
}

export interface SoftwareRequest {
	request_id: string;
	title: string;
	description: string;
	reason: string;
	status: 'pending' | 'assessed' | 'approved' | 'declined' | 'released' | string;
	created_at: string;
	assessment: Assessment | null;
	assessment_draft: boolean;
	resolved_by: string | null;
	resolution_reason: string | null;
	release_version: string | null;
}

// ── Onboarding tracker (Overview) ───────────────────────────────────────────

// One of MY tenant applications (coordinator GET /tenant-applications/mine).
// The one route that works for an UNREGISTERED key: the coordinator verifies
// the RFC 9421 signature against the request's own keyid (self-keyid proof of
// possession of the applying key), so the Overview can track an application
// before whoami ever succeeds. Newest first (coordinator orders created_at DESC).
export interface TenantApplication {
	application_id: string;
	status: 'pending' | 'approved' | 'declined' | string;
	resolution_reason: string | null;
	created_tenant_id: string | null;
}

// Local-operations (§8 browser-driven stand-up). These touch the researcher's
// OWN machine, not the coordinator: the experiment.toml config editor (Layer 2)
// and — gated by `exec_enabled` — the SDK Build/Submit/Run buttons (Layer 3).
export interface LocalStatus {
	workspace_set: boolean;
	workspace: string | null;
	workspace_exists: boolean;
	config_present: boolean;
	pkg_present: boolean;
	exec_enabled: boolean;
}

// experiment.toml as nested tables. Known keys are typed; unknown keys pass
// through (a tenant's bespoke [driver] knobs survive a form save server-side).
export interface ExperimentConfigTables {
	experiment?: Record<string, unknown>;
	executor?: Record<string, unknown>;
	reducer?: Record<string, unknown>;
	work_unit_source?: Record<string, unknown>;
	driver?: Record<string, unknown>;
	[table: string]: Record<string, unknown> | undefined;
}

export interface LocalConfig {
	present: boolean;
	config: ExperimentConfigTables;
}

// Layer 3: the dashboard shells the SDK. ExecResult is build/submit's captured
// output (ok=false on a non-zero exit — an outcome, not an HTTP error).
export interface ExecResult {
	ok: boolean;
	returncode: number;
	stdout: string;
	stderr: string;
	cmd: string[];
}

// The managed `run` process — the driver loop. `present:false` ⇒ none started.
// `running` + a growing log ⇒ working; `running` + a static log ⇒ idle between
// rounds; finished rc 0 ⇒ done; rc != 0 ⇒ failed. The driver pulse reads this.
export interface RunStatus {
	present: boolean;
	running?: boolean;
	pid?: number;
	returncode?: number | null;
	started_at?: string;
	cwd?: string;
	log_size?: number;
	log_tail?: string;
}

export const api = {
	listExperiments: () => getJson<{ experiments?: Experiment[] }>('/api/v0/experiments'),
	getExperiment: (id: string) =>
		getJson<Experiment>(`/api/v0/experiments/${encodeURIComponent(id)}`),
	getWorkUnits: (id: string) =>
		getJson<WorkUnits>(`/api/v0/experiments/${encodeURIComponent(id)}/work-units`),
	getExperimentReceipts: (id: string) =>
		getJson<{ receipts?: Receipt[] }>(
			`/api/v0/experiments/${encodeURIComponent(id)}/receipts`
		),
	getExperimentActivity: (id: string) =>
		getJson<ExperimentActivity>(`/api/v0/experiments/${encodeURIComponent(id)}/activity`),
	whoami: () => getJson<WhoAmI>('/api/v0/auth/whoami'),
	myWorkers: () => getJson<{ workers?: AccountWorker[] }>('/api/v0/accounts/me/workers'),
	// D8: begin linking ORCID — returns the authorize URL the browser opens.
	// The coordinator's callback redirects back here with ?orcid=linked.
	linkOrcidStart: () =>
		postJson<{ authorize_url: string }>('/api/v0/accounts/orcid/start'),
	// Onboarding tracker: my tenant applications, signed by the local key even
	// when it isn't bound yet (self-keyid proof of possession).
	listMyApplications: () =>
		getJson<{ applications?: TenantApplication[] }>('/api/v0/tenant-applications/mine'),

	// Lifecycle actions (R-D4). Each returns the updated Experiment. The
	// coordinator enforces own-tenant authorization + transition validity; an
	// invalid action surfaces as a `conflict`-kind ApiError with its real reason.
	pauseExperiment: (id: string) =>
		postJson<Experiment>(`/api/v0/experiments/${encodeURIComponent(id)}/actions/pause`),
	resumeExperiment: (id: string) =>
		postJson<Experiment>(`/api/v0/experiments/${encodeURIComponent(id)}/actions/resume`),
	finalizeExperiment: (id: string) =>
		postJson<Experiment>(
			`/api/v0/experiments/${encodeURIComponent(id)}/actions/finalize-submissions`
		),
	abortExperiment: (id: string) =>
		postJson<Experiment>(`/api/v0/experiments/${encodeURIComponent(id)}/actions/abort`),

	// Results delivery (R-D5). `include` is 'consensus' (default) or 'raw';
	// `cursor` follows the previous page's next_cursor.
	getResults: (id: string, opts: { include?: 'consensus' | 'raw'; cursor?: string } = {}) => {
		const q = new URLSearchParams();
		if (opts.include) q.set('include', opts.include);
		if (opts.cursor) q.set('cursor', opts.cursor);
		const qs = q.toString();
		return getJson<ResultList>(
			`/api/v0/experiments/${encodeURIComponent(id)}/results${qs ? `?${qs}` : ''}`
		);
	},
	// The evidence bundle (EB-1). Collecting transfers data custody to the
	// researcher. A `conflict` ApiError here is the verify-on-export tamper
	// alarm — the coordinator refused to sign custody over a set that fails
	// verification.
	// The Drift Benchmark (D16.4): score this experiment against a reference in
	// envelope units — computed server-side over two custody-verified bundles.
	benchmarkExperiment: (id: string, reference: string, label?: string, referenceLabel?: string) =>
		getJson<BenchmarkRecord>(
			`/api/v0/experiments/${encodeURIComponent(id)}/benchmark?reference=${encodeURIComponent(reference)}` +
				(label ? `&label=${encodeURIComponent(label)}` : '') +
				(referenceLabel ? `&reference_label=${encodeURIComponent(referenceLabel)}` : '')
		),
	listBenchmarks: () => getJson<{ benchmarks: BenchmarkSummary[] }>('/api/v0/benchmarks'),
	exportResults: (id: string, label?: string) =>
		getJson<ExportResponse>(
			`/api/v0/experiments/${encodeURIComponent(id)}/results/export` +
				(label ? `?label=${encodeURIComponent(label)}` : '')
		),

	// The result-set attestation (integrity panel, R-D inc-1). Final for a
	// completed experiment; `checkpoint: true` asks for a partial
	// consensus-so-far attestation mid-run. A `not_ready` ApiError means the
	// final attestation isn't available yet (experiment not completed).
	getAttestation: (id: string, opts: { checkpoint?: boolean } = {}) =>
		getJson<Attestation>(
			`/api/v0/experiments/${encodeURIComponent(id)}/attestation${
				opts.checkpoint ? '?checkpoint=true' : ''
			}`
		),

	getCitation: (id: string) =>
		getJson<Citation>(`/api/v0/experiments/${encodeURIComponent(id)}/citation`),

	// Demand board (R-D6, §9 #46): the researcher's push surface. GET lists are
	// tenant-scoped coordinator-side; submits enter the maintainer review queue.
	getCatalog: () =>
		getJson<{ models?: CatalogEntry[]; total_active_workers?: number }>('/api/v0/catalog'),
	listModelRequests: () =>
		getJson<{ requests?: ModelRequest[] }>('/api/v0/model-requests'),
	createModelRequest: (body: { model_id: string; reason: string; hf_repo?: string }) =>
		postJsonBody<ModelRequest>('/api/v0/model-requests', body),
	listSoftwareRequests: () =>
		getJson<{ requests?: SoftwareRequest[] }>('/api/v0/software-requests'),
	createSoftwareRequest: (body: { title: string; description: string; reason: string }) =>
		postJsonBody<SoftwareRequest>('/api/v0/software-requests', body),

	// ORCID-rooted onboarding (#16): submit a tenant application carrying the
	// ORCID implicit-flow access token + metadata. The backend signs it with the
	// local key (proof of possession) before forwarding to the coordinator.
	applyTenant: (body: {
		orcid_access_token: string;
		requested_tenant_id: string;
		contact_name: string;
		affiliation: string;
		research_summary?: string;
	}) => postJsonBody<{ application_id: string; status: string }>('/api/v0/tenant-applications', body),

	// Tier-1 connect (no tenant): bind this dashboard's key to an account via a
	// verified IdP token. The local key signs the request (proof of possession).
	bindAccount: (body: { idp: 'orcid' | 'github'; access_token: string }) =>
		postJsonBody<{
			account_id: string;
			idp?: string;
			display_name?: string;
			is_new_account?: boolean;
		}>('/api/v0/accounts/bind', body),
	githubDeviceStart: () =>
		postJson<{
			user_code: string;
			verification_uri: string;
			device_code: string;
			interval: number;
		}>('/api/v0/accounts/github/device/start'),
	githubDevicePoll: (device_code: string) =>
		postJsonBody<{ access_token?: string; status?: string; error?: string }>(
			'/api/v0/accounts/github/device/poll',
			{ device_code }
		),

	// Local-operations (§8). getLocalConfig returns {} when the file is absent;
	// saveLocalConfig merges the sent tables over any existing file server-side
	// (unmanaged tables/keys survive). An `unconfigured` ApiError means no
	// WORKSPACE_DIR — the page shows the CLI fallback instead of the form.
	getLocalStatus: () => getJson<LocalStatus>('/api/v0/local/status'),
	getLocalConfig: () => getJson<LocalConfig>('/api/v0/local/config'),
	saveLocalConfig: (config: ExperimentConfigTables) =>
		postJsonBody<{ written: string; config: ExperimentConfigTables }>(
			'/api/v0/local/config',
			config
		),

	// Layer 3 exec (gated by exec_enabled). build/submit are synchronous; run
	// starts the managed background driver. An `exec_disabled` ApiError means
	// LOCAL_EXEC isn't set — the page shows the buttons greyed with a hint.
	execBuild: () => postJson<ExecResult>('/api/v0/local/build'),
	execSubmit: () => postJson<ExecResult>('/api/v0/local/submit'),
	startRun: () => postJson<{ started: boolean; pid: number; cwd: string }>('/api/v0/local/run'),
	getRun: () => getJson<RunStatus>('/api/v0/local/run'),
	stopRun: () =>
		postJson<{ stopped: boolean; returncode: number | null }>('/api/v0/local/run/stop')
};
