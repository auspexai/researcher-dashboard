<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError, type SupportedEntry } from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';

	// The in-app demand-board was retired (design D2): requests live on the
	// AuspexAI community forum — GitHub Discussions. This page is the launchpad,
	// led by (1) what's ON the fleet right now and (2) the curated set the
	// network can provision on demand.
	const DISCUSSIONS = 'https://github.com/auspexai/.github/discussions';
	const NEW = 'https://github.com/auspexai/.github/discussions/new/choose';

	let models = $state<SupportedEntry[] | null>(null);
	let totalWorkers = $state<number | null>(null);
	let autoAcquire = $state(false);
	let catalogSource = $state<'hf' | 'curated' | null>(null);
	let catalogFetchedAt = $state<string | null>(null);
	let error = $state<ApiError | null>(null);

	// Two honest layers: on the fleet now (available) vs. provisionable.
	let onFleet = $derived((models ?? []).filter((m) => m.status === 'available'));
	let provisionable = $derived((models ?? []).filter((m) => m.status !== 'available'));

	onMount(async () => {
		try {
			const data = await api.getSupported();
			totalWorkers = data.total_active_workers ?? 0;
			autoAcquire = data.fleet_can_auto_acquire ?? false;
			catalogSource = data.catalog_source ?? null;
			catalogFetchedAt = data.catalog_fetched_at ?? null;
			models = data.models ?? []; // coordinator pre-sorts within each layer
		} catch (e) {
			error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		}
	});

	function fleetNote(m: SupportedEntry): string {
		return `on ${m.on_worker_count} worker${m.on_worker_count === 1 ? '' : 's'}`;
	}
	function provNote(m: SupportedEntry): string {
		if (m.status === 'too_big') return `needs a worker with ≥${m.approx_ram_gb} GB`;
		if (m.status === 'runnable')
			return m.fits_worker_count > 0
				? `runnable · fits ${m.fits_worker_count} worker${m.fits_worker_count === 1 ? '' : 's'}`
				: 'runnable';
		return 'capacity unknown';
	}
	const ram = (m: SupportedEntry) => (m.approx_ram_gb != null ? `~${m.approx_ram_gb} GB` : '');
	function refreshedNote(): string {
		if (catalogSource !== 'hf' || !catalogFetchedAt) return '';
		const d = new Date(catalogFetchedAt);
		return Number.isNaN(d.getTime())
			? ''
			: d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' });
	}
</script>

<h1>Requests</h1>
<p class="lead">
	What you can run on the network: the models already loaded on a worker, plus the curated set the
	fleet can provision on demand. For anything else, open a request on the AuspexAI community forum.
</p>

{#if error}
	<div class="card"><ErrorState {error} /></div>
{:else if models === null}
	<div class="card"><p class="muted">Loading…</p></div>
{:else}
	<section class="card">
		<div class="card-head">
			<h2>On the fleet now</h2>
			{#if totalWorkers !== null}
				<span class="pill">{totalWorkers} active worker{totalWorkers === 1 ? '' : 's'}</span>
			{/if}
		</div>
		<p class="sub">
			Models a worker already holds — ready to run, no download. The count is a rough availability
			signal: more workers means more capacity and corroboration.
		</p>
		{#if onFleet.length === 0}
			<p class="muted">No models are loaded on an active worker right now.</p>
		{:else}
			<ul class="models">
				{#each onFleet as m (m.model_id)}
					<li>
						<span class="dot available" title="available" aria-label="available"></span>
						<span class="name">
							<span class="display">{m.display_name}</span>
							{#if m.display_name !== m.model_id}<span class="model-id">{m.model_id}</span>{/if}
						</span>
						<span class="meta">
							<span class="status-note">{fleetNote(m)}</span>
							{#if ram(m)}<span class="rm">{ram(m)}</span>{/if}
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section class="card">
		<h2>Also provisionable</h2>
		<p class="sub">
			Models the network can pull on demand{autoAcquire
				? ' (workers acquire models automatically)'
				: ''}. <span class="dot runnable"></span> runnable on the current fleet ·
			<span class="dot too_big"></span> would need a bigger worker than any online.
		</p>
		{#if refreshedNote()}
			<p class="fresh">Polled from Hugging Face · refreshed {refreshedNote()}</p>
		{/if}
		{#if provisionable.length === 0}
			<p class="muted">Everything in the curated set is already on the fleet.</p>
		{:else}
			<ul class="models">
				{#each provisionable as m (m.model_id)}
					<li class:dim={m.status === 'too_big'}>
						<span class="dot {m.status}" title={m.status} aria-label={m.status}></span>
						<span class="name">
							<span class="display">{m.display_name}</span>
							{#if m.display_name !== m.model_id}<span class="model-id">{m.model_id}</span>{/if}
						</span>
						<span class="meta">
							<span class="status-note">{provNote(m)}</span>
							{#if ram(m)}<span class="rm">{ram(m)}</span>{/if}
						</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{/if}

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
	.fresh {
		color: #6f788f;
		font-size: 0.75rem;
		margin: -0.5rem 0 0.9rem;
		font-variant-numeric: tabular-nums;
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
		gap: 0.7rem;
		padding: 0.45rem 0.6rem;
		border: 1px solid #1a2336;
		border-radius: 6px;
		background: #0c1322;
	}
	.models li.dim {
		opacity: 0.55;
	}
	.dot {
		width: 9px;
		height: 9px;
		border-radius: 50%;
		flex: none;
	}
	.dot.available {
		background: #34d399;
	}
	.dot.runnable {
		background: transparent;
		border: 1.5px solid #4b9fd6;
	}
	.dot.unknown {
		background: transparent;
		border: 1.5px solid #55607a;
	}
	.dot.too_big {
		background: #3a4358;
	}
	.name {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		min-width: 0;
		flex: 1;
	}
	.display {
		color: #e6e9f0;
		font-size: 0.9rem;
		font-weight: 500;
		word-break: break-all;
	}
	.model-id {
		color: #8b93a7;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 0.72rem;
		word-break: break-all;
	}
	.meta {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 0.1rem;
		white-space: nowrap;
	}
	.status-note {
		color: #b8bfd0;
		font-size: 0.78rem;
	}
	.rm {
		color: #8b93a7;
		font-size: 0.72rem;
		font-variant-numeric: tabular-nums;
	}
	.sub .dot {
		display: inline-block;
		vertical-align: middle;
		margin: 0 0.05rem 0 0.35rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
		max-width: 64ch;
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
	.note {
		margin-top: 1rem;
	}
</style>
