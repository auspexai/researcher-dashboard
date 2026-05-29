<script lang="ts">
	import { page } from '$app/state';
	import { api, ApiError, type Experiment, type WorkUnits } from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';

	const id = $derived(page.params.id);

	let experiment = $state<Experiment | null>(null);
	let workUnits = $state<WorkUnits | null>(null);
	let error = $state<ApiError | null>(null);
	let loading = $state(true);

	const fmt = (iso: string | undefined) => (iso ? new Date(iso).toLocaleString() : '—');

	// Re-fetch whenever the route id changes. Work-units may legitimately be
	// empty (none submitted yet), so a work-units failure is non-fatal — we
	// still render the experiment detail.
	$effect(() => {
		const current = id;
		if (!current) return;
		loading = true;
		error = null;
		experiment = null;
		workUnits = null;
		(async () => {
			try {
				experiment = await api.getExperiment(current);
				try {
					workUnits = await api.getWorkUnits(current);
				} catch {
					workUnits = null;
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
</style>
