<script lang="ts">
	import { page } from '$app/state';
	import {
		api,
		ApiError,
		type Experiment,
		type ExperimentActivity,
		type Receipt,
		type WorkUnits
	} from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';

	const id = $derived(page.params.id);

	let experiment = $state<Experiment | null>(null);
	let workUnits = $state<WorkUnits | null>(null);
	let activity = $state<ExperimentActivity | null>(null);
	let receipts = $state<Receipt[] | null>(null);
	let error = $state<ApiError | null>(null);
	let loading = $state(true);

	// Lifecycle actions (R-D4): `acting` is the in-flight action name (disables
	// the row); `confirming` is the destructive action awaiting confirmation;
	// `actionError` surfaces a refused action (e.g. a `conflict` reason).
	let acting = $state<string | null>(null);
	let confirming = $state<string | null>(null);
	let actionError = $state<ApiError | null>(null);

	const fmt = (iso: string | undefined) => (iso ? new Date(iso).toLocaleString() : '—');

	// Load the experiment + its (independently non-fatal) secondary views. On the
	// initial/route-change load we show the full loading state; a post-action
	// refetch is `silent` so the page doesn't flash back to "Loading…".
	async function load(current: string, opts: { silent?: boolean } = {}) {
		if (!opts.silent) {
			loading = true;
			error = null;
			experiment = null;
			workUnits = null;
			activity = null;
			receipts = null;
		}
		try {
			experiment = await api.getExperiment(current);
			try {
				workUnits = await api.getWorkUnits(current);
			} catch {
				/* secondary — keep prior value */
			}
			try {
				activity = await api.getExperimentActivity(current);
			} catch {
				/* secondary — keep prior value */
			}
			try {
				receipts = (await api.getExperimentReceipts(current)).receipts ?? [];
			} catch {
				/* secondary — keep prior value */
			}
		} catch (e) {
			if (!opts.silent) error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			if (!opts.silent) loading = false;
		}
	}

	// Run a lifecycle action, then silently refetch so the status badge + fields
	// reflect the new state. A refused action (conflict / unauthorized) is shown
	// inline without disturbing the loaded page.
	async function act(name: string, fn: (id: string) => Promise<unknown>) {
		const current = id;
		if (!current || acting) return;
		acting = name;
		actionError = null;
		confirming = null;
		try {
			await fn(current);
			await load(current, { silent: true });
		} catch (e) {
			actionError = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			acting = null;
		}
	}

	// Re-fetch whenever the route id changes.
	$effect(() => {
		const current = id;
		if (!current) return;
		actionError = null;
		confirming = null;
		load(current);
	});

	const counts = $derived(workUnits?.counts_by_status ?? {});
	const totalUnits = $derived(Object.values(counts).reduce((a, b) => a + b, 0));

	// Replication fill as a 0–100% bar; guard against divide-by-zero pre-activity.
	const fillPct = $derived(
		activity?.replication_target_total
			? Math.min(
					100,
					Math.round(((activity.completions_total ?? 0) / activity.replication_target_total) * 100)
				)
			: 0
	);

	// Researcher-actionable transitions, gated on the coordinator's transition
	// map (approve/archive are maintainer-only and intentionally absent).
	const status = $derived(experiment?.status);
	const canPause = $derived(status === 'approved');
	const canResume = $derived(status === 'paused');
	const canFinalize = $derived(
		(status === 'approved' || status === 'paused') && !experiment?.submissions_finalized
	);
	const canAbort = $derived(status === 'submitted' || status === 'approved' || status === 'paused');
	const hasActions = $derived(canPause || canResume || canFinalize || canAbort);
</script>

<p class="back"><a href="/experiments">← My Experiments</a></p>

{#if loading}
	<p class="muted">Loading…</p>
{:else if error}
	<ErrorState {error} />
{:else if experiment}
	<div class="head">
		<h1>{experiment.tenant_experiment_label ?? experiment.experiment_id}</h1>
		<StatusBadge status={experiment.status} />
	</div>
	<p class="id">{experiment.experiment_id}</p>

	{#if hasActions}
		<div class="actions">
			{#if canPause}
				<button class="act" onclick={() => act('pause', api.pauseExperiment)} disabled={!!acting}>
					{acting === 'pause' ? 'Pausing…' : 'Pause'}
				</button>
			{/if}
			{#if canResume}
				<button class="act" onclick={() => act('resume', api.resumeExperiment)} disabled={!!acting}>
					{acting === 'resume' ? 'Resuming…' : 'Resume'}
				</button>
			{/if}
			{#if canFinalize}
				{#if confirming === 'finalize'}
					<span class="confirm">
						Finalize submissions? No more work units can be added afterward.
						<button class="act danger" onclick={() => act('finalize', api.finalizeExperiment)} disabled={!!acting}>
							{acting === 'finalize' ? 'Finalizing…' : 'Confirm'}
						</button>
						<button class="act ghost" onclick={() => (confirming = null)} disabled={!!acting}>Cancel</button>
					</span>
				{:else}
					<button class="act" onclick={() => (confirming = 'finalize')} disabled={!!acting}>
						Finalize submissions
					</button>
				{/if}
			{/if}
			{#if canAbort}
				{#if confirming === 'abort'}
					<span class="confirm">
						Abort this experiment? This cannot be undone.
						<button class="act danger" onclick={() => act('abort', api.abortExperiment)} disabled={!!acting}>
							{acting === 'abort' ? 'Aborting…' : 'Confirm abort'}
						</button>
						<button class="act ghost" onclick={() => (confirming = null)} disabled={!!acting}>Cancel</button>
					</span>
				{:else}
					<button class="act danger-outline" onclick={() => (confirming = 'abort')} disabled={!!acting}>
						Abort
					</button>
				{/if}
			{/if}
		</div>
		{#if actionError}
			<p class="action-error" class:conflict={actionError.kind === 'conflict'}>{actionError.message}</p>
		{/if}
	{/if}

	<section class="grid">
		<div class="field"><span class="k">Submitted</span><span class="v">{fmt(experiment.submitted_at)}</span></div>
		<div class="field"><span class="k">Started</span><span class="v">{fmt(experiment.started_at)}</span></div>
		<div class="field"><span class="k">Completed</span><span class="v">{fmt(experiment.completed_at)}</span></div>
		<div class="field"><span class="k">Submissions</span><span class="v">{experiment.submissions_finalized ? 'finalized' : 'open'}</span></div>
		<div class="field"><span class="k">Integrity policy</span><span class="v">{experiment.integrity_policy ?? '—'}</span></div>
		<div class="field"><span class="k">Revision</span><span class="v">{experiment.revision ?? '—'}</span></div>
		{#if experiment.last_action_at}
			<div class="field">
				<span class="k">Last action</span>
				<span class="v">{fmt(experiment.last_action_at)} · {experiment.last_action_by_class ?? '—'}</span>
			</div>
		{/if}
		{#if experiment.manifest_hash}
			<div class="field wide">
				<span class="k">Manifest hash</span><span class="v mono">{experiment.manifest_hash}</span>
			</div>
		{/if}
	</section>

	<h2>Activity</h2>
	{#if !activity}
		<p class="muted">No activity yet.</p>
	{:else}
		<div class="counts">
			<div class="count">
				<span class="n">{activity.active_contributor_count ?? 0}</span>
				<span class="label">active contributors</span>
			</div>
			<div class="count">
				<span class="n">{activity.completions_total ?? 0}/{activity.replication_target_total ?? 0}</span>
				<span class="label">replication fill</span>
			</div>
			<div class="count">
				<span class="n">{activity.total_work_units ?? 0}</span>
				<span class="label">work units</span>
			</div>
			{#if activity.network_active_workers != null}
				<div class="count" title="Workers active network-wide (heartbeat-fresh, not retired or quarantined).">
					<span class="n">{activity.network_active_workers}</span>
					<span class="label">network workers</span>
				</div>
			{/if}
		</div>
		{#if activity.replication_target_total}
			<div class="bar" title="{fillPct}% replicated">
				<div class="bar-fill" style="width: {fillPct}%"></div>
			</div>
		{/if}
		<p class="muted last-activity">
			Last activity: {fmt(activity.last_activity_at)}
		</p>
		<p class="anon-note">
			Contributor count is anonymized — a tenant cannot see which volunteers ran its work.
		</p>

		{#if activity.own_workers && activity.own_workers.length > 0}
			<h3>Your workers</h3>
			<p class="muted">
				{activity.own_workers.length} of your own-account {activity.own_workers.length === 1
					? 'worker is'
					: 'workers are'} backing this experiment.
			</p>
			<table class="workers">
				<thead>
					<tr><th>Worker</th><th>Tier</th><th>Status</th><th>Results</th><th>Last activity</th></tr>
				</thead>
				<tbody>
					{#each activity.own_workers as w (w.worker_id)}
						<tr>
							<td>
								<span class="wid">{w.worker_id}</span>
								<span class="mono pk">{w.worker_pubkey_hex.slice(0, 16)}…</span>
							</td>
							<td>T{w.trust_tier}</td>
							<td>
								<StatusBadge status={w.status} />
								{#if w.status === 'quarantined' && w.quarantine_reason}
									<div class="reason" title="Quarantine reason set by the maintainer.">
										{w.quarantine_reason}
									</div>
								{/if}
							</td>
							<td>{w.result_count}</td>
							<td class="muted">{fmt(w.last_activity_at)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	{/if}

	<h2>Work units</h2>
	{#if totalUnits === 0}
		<p class="muted">No work units submitted yet.</p>
	{:else}
		<p class="muted">{totalUnits} total</p>
		<div class="counts">
			{#each Object.entries(counts) as [status, n] (status)}
				<div class="count">
					<span class="n">{n}</span>
					<StatusBadge {status} />
				</div>
			{/each}
		</div>
	{/if}

	<h2>Receipts</h2>
	{#if receipts === null}
		<p class="muted">Receipts unavailable.</p>
	{:else if receipts.length === 0}
		<p class="muted">No receipts issued yet — they appear as volunteers complete work.</p>
	{:else}
		<p class="muted">{receipts.length} issued</p>
		<table class="receipts">
			<thead>
				<tr><th>Receipt</th><th>Issued</th></tr>
			</thead>
			<tbody>
				{#each receipts as r (r.receipt_id)}
					<tr>
						<td class="mono">{r.receipt_id}</td>
						<td class="muted">{fmt(r.issued_at)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
{/if}

<style>
	.back {
		margin: 0 0 0.5rem;
	}
	.back a {
		color: #8b93a7;
		text-decoration: none;
		font-size: 0.85rem;
	}
	.back a:hover {
		color: #b8bfd0;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	h1 {
		font-weight: 700;
		margin: 0;
	}
	.id {
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		color: #6b7390;
		margin: 0.25rem 0 0;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin: 1rem 0 0;
	}
	.act {
		font: inherit;
		font-size: 0.82rem;
		padding: 0.4rem 0.8rem;
		border-radius: 6px;
		border: 1px solid #2a3550;
		background: #141b2c;
		color: #e6e9f0;
		cursor: pointer;
	}
	.act:hover:not(:disabled) {
		border-color: #4a7dff;
	}
	.act:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.act.danger {
		border-color: #b4434f;
		background: #b4434f;
		color: #fff;
	}
	.act.danger:hover:not(:disabled) {
		border-color: #d05561;
		background: #d05561;
	}
	.act.danger-outline {
		border-color: #7a2e36;
		background: transparent;
		color: #f7a6ad;
	}
	.act.danger-outline:hover:not(:disabled) {
		border-color: #b4434f;
		background: #b4434f;
		color: #fff;
	}
	.act.ghost {
		background: transparent;
		border-color: #2a3550;
		color: #8b93a7;
	}
	.confirm {
		display: inline-flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		font-size: 0.82rem;
		color: #cbd2e0;
		background: #0e1424;
		border: 1px solid #2a3550;
		border-radius: 6px;
		padding: 0.35rem 0.6rem;
	}
	.action-error {
		margin: 0.6rem 0 0;
		font-size: 0.83rem;
		color: #f7a6ad;
	}
	/* A conflict is an expected "can't do that from this state" refusal — amber,
	   not the red reserved for transport/auth failures. */
	.action-error.conflict {
		color: #fbbf24;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.75rem;
		margin: 1.25rem 0;
	}
	.field {
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.6rem 0.8rem;
		background: #0e1424;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.field.wide {
		grid-column: 1 / -1;
	}
	.k {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
	}
	.v {
		color: #e6e9f0;
		font-size: 0.9rem;
	}
	.v.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.78rem;
		word-break: break-all;
		color: #b8bfd0;
	}
	h2 {
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b93a7;
		margin: 1.5rem 0 0.5rem;
	}
	h3 {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
		margin: 1.1rem 0 0.4rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.counts {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}
	.count {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.5rem 0.8rem;
		background: #0e1424;
	}
	.n {
		font-size: 1.25rem;
		font-weight: 700;
		color: #e6e9f0;
	}
	.count .label {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
	}
	.bar {
		height: 8px;
		background: #1e2638;
		border-radius: 4px;
		overflow: hidden;
		margin: 0.75rem 0 0.25rem;
	}
	.bar-fill {
		height: 100%;
		background: #4a7dff;
		transition: width 0.3s ease;
	}
	.last-activity {
		margin: 0.5rem 0 0;
	}
	.anon-note {
		color: #6b7390;
		font-size: 0.72rem;
		margin: 0.35rem 0 0;
	}
	table.receipts,
	table.workers {
		width: 100%;
		border-collapse: collapse;
		margin-top: 0.5rem;
	}
	table.receipts th,
	table.workers th {
		text-align: left;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #1e2638;
	}
	table.receipts td,
	table.workers td {
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #141b2c;
		font-size: 0.85rem;
		color: #e6e9f0;
	}
	.wid {
		color: #e6e9f0;
	}
	.pk {
		display: block;
		font-family: ui-monospace, monospace;
		font-size: 0.7rem;
		color: #6b7390;
	}
	.reason {
		margin-top: 0.25rem;
		font-size: 0.74rem;
		color: #fbbf24;
		max-width: 22rem;
	}
	td.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.78rem;
		color: #b8bfd0;
	}
</style>
