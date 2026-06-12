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
	| 'client_error';

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
	exportResults: (id: string) =>
		getJson<ExportBundle>(`/api/v0/experiments/${encodeURIComponent(id)}/results/export`),

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
		postJsonBody<SoftwareRequest>('/api/v0/software-requests', body)
};
