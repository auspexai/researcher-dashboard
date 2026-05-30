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

async function getJson<T>(path: string): Promise<T> {
	let resp: Response;
	try {
		resp = await fetch(path);
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

// Mirrors the coordinator's ExperimentActivityResponse (R-D3). Every field is
// an aggregate count or timestamp — no per-worker identity.
export interface ExperimentActivity {
	experiment_id?: string;
	active_contributor_count?: number;
	total_work_units?: number;
	work_unit_counts?: Record<string, number>;
	last_activity_at?: string;
	completions_total?: number;
	replication_target_total?: number;
}

// The confirmed bound identity from the coordinator's /auth/whoami. For a
// researcher: credential_class="researcher" + their own tenant_id + pubkey_hex.
export interface WhoAmI {
	credential_class: string;
	tenant_id?: string;
	pubkey_hex?: string;
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
	whoami: () => getJson<WhoAmI>('/api/v0/auth/whoami')
};
