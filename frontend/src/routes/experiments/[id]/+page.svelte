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

	const fmt = (iso: string | undefined) => (iso ? new Date(iso).toLocaleString() : '—');

	// Re-fetch whenever the route id changes. Work-units, activity, and receipts
	// may legitimately be empty (none submitted yet), so each secondary fetch is
	// non-fatal — only a failure to load the experiment itself is fatal.
	$effect(() => {
		const current = id;
		if (!current) return;
		loading = true;
		error = null;
		experiment = null;
		workUnits = null;
		activity = null;
		receipts = null;
		(async () => {
			try {
				experiment = await api.getExperiment(current);
				try {
					workUnits = await api.getWorkUnits(current);
				} catch {
					workUnits = null;
				}
				try {
					activity = await api.getExperimentActivity(current);
				} catch {
					activity = null;
				}
				try {
					receipts = (await api.getExperimentReceipts(current)).receipts ?? [];
				} catch {
					receipts = null;
				}
			} catch (e) {
				error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
			} finally {
				loading = false;
			}
		})();
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
					<tr><th>Worker</th><th>Tier</th><th>Results</th><th>Last activity</th></tr>
				</thead>
				<tbody>
					{#each activity.own_workers as w (w.worker_id)}
						<tr>
							<td>
								<span class="wid">{w.worker_id}</span>
								<span class="mono pk">{w.worker_pubkey_hex.slice(0, 16)}…</span>
							</td>
							<td>T{w.trust_tier}</td>
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
	td.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.78rem;
		color: #b8bfd0;
	}
</style>
