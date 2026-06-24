<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError, type CatalogEntry } from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';

	// The in-app demand-board was retired (design D2): requests live on the
	// AuspexAI community forum — GitHub Discussions — a public, votable place
	// maintainers triage alongside the code. This page is the launchpad, led by
	// a live view of what the network can already serve so you don't request a
	// model the fleet already runs.
	const DISCUSSIONS = 'https://github.com/auspexai/.github/discussions';
	const NEW = 'https://github.com/auspexai/.github/discussions/new/choose';

	let models = $state<CatalogEntry[] | null>(null);
	let totalWorkers = $state<number | null>(null);
	let error = $state<ApiError | null>(null);

	onMount(async () => {
		try {
			const data = await api.getCatalog();
			totalWorkers = data.total_active_workers ?? 0;
			// Most-corroborated first: more workers = more capacity + redundancy.
			models = (data.models ?? []).sort(
				(a, b) => b.worker_count - a.worker_count || a.model_id.localeCompare(b.model_id)
			);
		} catch (e) {
			error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		}
	});
</script>

<h1>Requests</h1>
<p class="lead">
	Before requesting a model, check what the network can already serve. For anything missing, open a
	request on the AuspexAI community forum — a public place maintainers triage alongside the code.
</p>

<section class="card">
	<div class="card-head">
		<h2>Available on the network now</h2>
		{#if totalWorkers !== null && !error}
			<span class="pill">{totalWorkers} active worker{totalWorkers === 1 ? '' : 's'}</span>
		{/if}
	</div>
	<p class="sub">
		Models the fleet can serve right now — no request needed. The worker count is a rough
		availability signal: more workers means more capacity and corroboration for your runs.
	</p>

	{#if error}
		<ErrorState {error} />
	{:else if models === null}
		<p class="muted">Loading…</p>
	{:else if models.length === 0}
		<p class="muted">
			Nothing is being served right now — no active worker is holding a model. If you need one, open
			a model request below.
		</p>
	{:else}
		<ul class="models">
			{#each models as m (m.model_id)}
				<li>
					<span class="model-id">{m.model_id}</span>
					<span class="count">{m.worker_count} worker{m.worker_count === 1 ? '' : 's'}</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<div class="card">
	<p class="kinds-intro">Don't see what you need? Two kinds of request:</p>
	<ul class="kinds">
		<li>
			<strong>Model requests</strong> — a model (and quantization) you want for your experiments
			that isn't listed above.
		</li>
		<li>
			<strong>Capability requests</strong> — something the platform can't do yet that your
			research needs.
		</li>
	</ul>
	<div class="actions">
		<a class="cta" href={NEW} target="_blank" rel="noopener noreferrer">Open a request ↗</a>
		<a class="ghost" href={DISCUSSIONS} target="_blank" rel="noopener noreferrer"
			>Browse all requests ↗</a
		>
	</div>
</div>

<p class="muted note">
	Posting in the open lets other researchers up-vote and add detail, so the maintainers can see real
	demand. Your GitHub identity is your handle there.
</p>

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
		max-width: 64ch;
	}
	.card {
		border: 1px solid #1e2638;
		border-radius: 8px;
		background: #10182a;
		padding: 1.1rem 1.25rem;
		margin: 1rem 0;
		max-width: 64ch;
	}
	.card-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.75rem;
	}
	h2 {
		font-size: 1rem;
		font-weight: 600;
		color: #e6e9f0;
		margin: 0;
	}
	.pill {
		font-size: 0.78rem;
		color: #b8bfd0;
		background: #0c1322;
		border: 1px solid #1e2638;
		border-radius: 999px;
		padding: 0.15rem 0.6rem;
		white-space: nowrap;
	}
	.sub {
		color: #9aa3b8;
		font-size: 0.85rem;
		margin: 0.35rem 0 0.9rem;
		max-width: 60ch;
	}
	.models {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
	}
	.models li {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		padding: 0.4rem 0.6rem;
		border: 1px solid #1a2336;
		border-radius: 6px;
		background: #0c1322;
	}
	.model-id {
		color: #e6e9f0;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 0.85rem;
		word-break: break-all;
	}
	.count {
		color: #8b93a7;
		font-size: 0.8rem;
		white-space: nowrap;
	}
	.kinds-intro {
		color: #e6e9f0;
		margin: 0 0 0.4rem;
		font-weight: 600;
		font-size: 0.9rem;
	}
	.kinds {
		margin: 0 0 1rem;
		padding-left: 1.1rem;
		color: #cdd5e6;
		font-size: 0.9rem;
	}
	.kinds li {
		margin: 0.3rem 0;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
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
	a.ghost {
		color: #7aa2ff;
		border: 1px solid #2a3450;
		border-radius: 6px;
		padding: 0.45rem 1rem;
		text-decoration: none;
		font-size: 0.9rem;
	}
	a.ghost:hover {
		border-color: #3a4668;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
		max-width: 64ch;
	}
	.note {
		margin-top: 1rem;
	}
</style>
