<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { api, ApiError, type Experiment } from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import ExperimentSetup from '$lib/components/ExperimentSetup.svelte';

	// The launcher home: start a run (Vigiles starter or your own workspace) here.
	// Monitoring lives on My Experiments — this page lists your recent runs only
	// as quick links into that detail view (the design's launcher/monitor split).
	let experiments = $state<Experiment[] | null>(null);
	let error = $state<ApiError | null>(null);

	const fmt = (iso: string | undefined) => (iso ? new Date(iso).toLocaleString() : '—');

	onMount(async () => {
		try {
			const data = await api.listExperiments();
			// Newest first; the launcher only needs a recent handful.
			experiments = (data.experiments ?? []).sort((a, b) =>
				(b.submitted_at ?? '').localeCompare(a.submitted_at ?? '')
			);
		} catch (e) {
			error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		}
	});

	const recent = $derived(experiments?.slice(0, 5) ?? []);
</script>

<h1>Run Experiment</h1>
<p class="lead">Start a run — the certified Vigiles starter, or your own workspace.</p>

<!-- Pinned: the declawed certified starter. Always available, for a first run
     and forever after. Its sub-page is the what-is-Vigiles + how-to hub. -->
<div class="starter">
	<div class="starter-head">
		<span class="badge">certified starter</span>
		<h2>Vigiles</h2>
	</div>
	<p class="starter-desc">
		A curated, declawed drift-probe experiment that runs out of the box — no code to write.
		It exercises the whole loop (submit → replicated execution → consensus → a verified,
		Rekor-anchored evidence bundle) so you can see the network work end-to-end before bringing
		your own tenant.
	</p>
	<div class="starter-actions">
		<a class="cta" href="/run/vigiles">Learn &amp; run Vigiles →</a>
		<span class="hint">low-risk · package-bound · any R1+ researcher</span>
	</div>
</div>

<!-- The run controls: build → submit → run the configured workspace (the Vigiles
     starter or your own). Gates itself on the workspace / local-exec state. -->
<h2 class="section">Run your workspace</h2>
<ExperimentSetup />

<!-- Recent runs: quick links into the monitor (My Experiments). -->
<div class="recent-head">
	<h2 class="section">Recent runs</h2>
	<a class="all" href="/experiments">All experiments →</a>
</div>
{#if error}
	<ErrorState {error} />
{:else if experiments === null}
	<p class="muted">Loading…</p>
{:else if recent.length === 0}
	<p class="muted">No runs yet — start the Vigiles starter above, or stand up your own.</p>
{:else}
	<table>
		<thead>
			<tr><th>Experiment</th><th>Status</th><th>Submitted</th></tr>
		</thead>
		<tbody>
			{#each recent as exp (exp.experiment_id)}
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
					<td><StatusBadge status={exp.status} /></td>
					<td class="muted">{fmt(exp.submitted_at)}</td>
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
	.section {
		font-size: 0.95rem;
		margin: 1.5rem 0 0.5rem;
		color: #e6e9f0;
	}
	.starter {
		border: 1px solid #1d7f90;
		border-left-width: 4px;
		border-radius: 8px;
		background: linear-gradient(180deg, rgba(21, 94, 107, 0.18), #10182a);
		padding: 1.1rem 1.25rem;
		margin: 1rem 0 0.5rem;
	}
	.starter-head {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.starter-head h2 {
		margin: 0;
		font-size: 1.25rem;
		color: #e0fbff;
	}
	.badge {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #67e8f9;
		border: 1px solid #1d7f90;
		border-radius: 999px;
		padding: 0.1rem 0.5rem;
	}
	.starter-desc {
		color: #cdd5e6;
		font-size: 0.9rem;
		margin: 0.6rem 0 0.9rem;
		max-width: 60ch;
	}
	.starter-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}
	a.cta {
		background: #155e6b;
		color: #e0fbff;
		border: 1px solid #1d7f90;
		border-radius: 6px;
		padding: 0.45rem 1rem;
		text-decoration: none;
		font-weight: 600;
		font-size: 0.9rem;
	}
	a.cta:hover {
		background: #1a6f7e;
	}
	.hint {
		color: #8b93a7;
		font-size: 0.8rem;
	}
	.recent-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 1rem;
	}
	a.all {
		color: #7aa2ff;
		text-decoration: none;
		font-size: 0.85rem;
	}
	a.all:hover {
		text-decoration: underline;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		margin-top: 0.5rem;
	}
	th {
		text-align: left;
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #8b93a7;
		border-bottom: 1px solid #1e2638;
		padding: 0.4rem 0.6rem;
	}
	tbody tr {
		cursor: pointer;
		border-bottom: 1px solid #141c2e;
	}
	tbody tr:hover {
		background: #131c30;
	}
	td {
		padding: 0.55rem 0.6rem;
		vertical-align: middle;
	}
	.label {
		display: block;
		color: #e2e8f0;
	}
	.id {
		display: block;
		font-family: ui-monospace, monospace;
		font-size: 0.72rem;
		color: #6b7390;
	}
</style>
