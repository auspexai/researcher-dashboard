<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError, type Experiment } from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';

	let experiments = $state<Experiment[] | null>(null);
	let error = $state<ApiError | null>(null);
	// Each run's drift score vs its declared reference (saved reports; a run
	// scored against several references shows its declared/most recent one).
	let benchByExp = $state<Record<string, number | null>>({});

	const fmt = (iso: string | undefined) => (iso ? new Date(iso).toLocaleString() : '—');

	onMount(async () => {
		try {
			const data = await api.listExperiments();
			// Newest first: most recently submitted at the top, oldest at the bottom.
			experiments = (data.experiments ?? []).sort((a, b) =>
				(b.submitted_at ?? '').localeCompare(a.submitted_at ?? '')
			);
		} catch (e) {
			error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		}
		try {
			const map: Record<string, number | null> = {};
			for (const b of (await api.listBenchmarks()).benchmarks) {
				const id = b.observation?.experiment_id;
				if (id && !(id in map)) map[id] = b.peak_eu ?? null; // newest-first wins
			}
			benchByExp = map;
		} catch {
			/* the column just stays empty — benchmarks are supplementary here */
		}
	});
</script>

<h1>My Experiments</h1>
<p class="lead">
	Experiments running under your tenant on the AuspexAI network. Start a new run on the
	<a href="/run">Run Experiment</a> page.
</p>

{#if error}
	<ErrorState {error} />
{:else if experiments === null}
	<p class="muted">Loading…</p>
{:else if experiments.length === 0}
	<div class="empty">
		<p>No experiments yet.</p>
		<p class="muted">
			Start one on the <a href="/run">Run Experiment</a> page — the Vigiles starter, or your own
			workspace. It appears here once the coordinator accepts it.
		</p>
	</div>
{:else}
	<table>
		<thead>
			<tr>
				<th>Experiment</th>
				<th>Status</th>
				<th>Drift</th>
				<th>Submitted</th>
				<th>Submissions</th>
			</tr>
		</thead>
		<tbody>
			{#each experiments as exp (exp.experiment_id)}
				<tr
					tabindex="0"
					role="link"
					onclick={() => goto(`/experiments/${exp.experiment_id}`)}
					onkeydown={(e) => e.key === 'Enter' && goto(`/experiments/${exp.experiment_id}`)}
				>
					<td>
						<span class="label">{exp.tenant_experiment_label ?? exp.experiment_id}</span>
						<span class="id">{exp.experiment_id}</span>
					</td>
					<td><StatusBadge status={exp.status} phase={exp.run_phase} /></td>
					<td class="mono" title="peak drift vs the run's declared reference, in envelope units">
						{benchByExp[exp.experiment_id] != null
							? `${benchByExp[exp.experiment_id]?.toFixed(2)} EU`
							: exp.experiment_id in benchByExp
								? 'n/a'
								: '—'}
					</td>
					<td class="muted">{fmt(exp.submitted_at)}</td>
					<td class="muted">{exp.submissions_finalized ? 'finalized' : 'open'}</td>
				</tr>
			{/each}
		</tbody>
	</table>
{/if}

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.empty {
		border: 1px dashed #1e2638;
		border-radius: 8px;
		padding: 1.5rem;
		text-align: center;
		margin-top: 1rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		margin-top: 1rem;
		font-size: 0.9rem;
	}
	th {
		text-align: left;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b93a7;
		font-weight: 600;
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid #1e2638;
	}
	td {
		padding: 0.65rem 0.75rem;
		border-bottom: 1px solid #141a28;
	}
	tbody tr {
		cursor: pointer;
	}
	tbody tr:hover {
		background: #0e1424;
	}
	tbody tr:focus-visible {
		outline: 2px solid #a78bfa;
		outline-offset: -2px;
	}
	.label {
		display: block;
		color: #e6e9f0;
	}
	.id {
		display: block;
		font-family: ui-monospace, monospace;
		font-size: 0.72rem;
		color: #6b7390;
	}
</style>
