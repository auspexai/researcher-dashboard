<script lang="ts">
	import { onMount } from 'svelte';

	type Health = {
		version: string;
		phase: string;
		coord: { url: string; reachable: boolean | null; detail: string | null };
		identity: { key_path: string; key_present: boolean };
	};

	let health = $state<Health | null>(null);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			const r = await fetch('/api/v0/health');
			health = await r.json();
		} catch (e) {
			error = String(e);
		}
	});
</script>

<h1>Overview</h1>
<p class="lead">
	Your local, tenant-scoped view of what your research is doing on the AuspexAI network.
</p>

{#if error}
	<p class="err">Could not reach the local backend: {error}</p>
{:else if !health}
	<p class="muted">Loading…</p>
{:else}
	<div class="grid">
		<div class="card">
			<h2>Identity</h2>
			{#if health.identity.key_present}
				<p class="ok">Tenant key found</p>
			{:else}
				<p class="warn">No tenant key</p>
				<p class="muted">
					Run <code>auspexai-tenant key generate</code> once your tenant is approved.
				</p>
			{/if}
			<p class="path">{health.identity.key_path}</p>
		</div>
		<div class="card">
			<h2>Coordinator</h2>
			{#if health.coord.reachable}
				<p class="ok">Reachable</p>
			{:else}
				<p class="warn">Unreachable</p>
			{/if}
			<p class="path">{health.coord.url}</p>
			{#if health.coord.detail}<p class="muted">{health.coord.detail}</p>{/if}
		</div>
	</div>
	<p class="footer muted">{health.phase} · v{health.version}</p>
{/if}

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 1rem;
		margin-top: 1rem;
	}
	.card {
		border: 1px solid #1e2638;
		border-radius: 8px;
		padding: 1rem 1.25rem;
		background: #0e1424;
	}
	.card h2 {
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b93a7;
		margin: 0 0 0.5rem;
	}
	.ok {
		color: #6ee7b7;
		margin: 0.25rem 0;
	}
	.warn {
		color: #fbbf24;
		margin: 0.25rem 0;
	}
	.err {
		color: #fca5a5;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.path {
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		color: #6b7390;
		word-break: break-all;
	}
	code {
		background: #1a2236;
		padding: 0.1rem 0.3rem;
		border-radius: 3px;
	}
	.footer {
		margin-top: 1.5rem;
	}
</style>
