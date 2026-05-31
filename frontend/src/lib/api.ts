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

async function request<T>(path: string, method: 'GET' | 'POST'): Promise<T> {
	let resp: Response;
	try {
		resp = await fetch(path, { method });
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
		postJson<Experiment>(`/api/v0/experiments/${encodeURIComponent(id)}/actions/abort`)
};
