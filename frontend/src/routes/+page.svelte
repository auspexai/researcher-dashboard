<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError, type WhoAmI } from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';

	type Health = {
		version: string;
		phase: string;
		coord: { url: string; reachable: boolean | null; detail: string | null };
		identity: { key_path: string; key_present: boolean; pubkey_hex: string | null };
	};

	let health = $state<Health | null>(null);
	let healthError = $state<string | null>(null);
	let whoami = $state<WhoAmI | null>(null);
	let whoamiError = $state<ApiError | null>(null);

	// pubkeys are 64 hex chars; show head…tail, full string on hover.
	const short = (k: string | null | undefined) => (k ? `${k.slice(0, 10)}…${k.slice(-8)}` : '—');

	onMount(async () => {
		try {
			health = await (await fetch('/api/v0/health')).json();
		} catch (e) {
			healthError = String(e);
			return;
		}
		// whoami is a signed coordinator round-trip — only attempt with a key present.
		if (health?.identity.key_present) {
			try {
				whoami = await api.whoami();
			} catch (e) {
				whoamiError = e instanceof ApiError ? e : new ApiError('client_error', String(e));
			}
		}
	});

	const local = $derived(health?.identity.pubkey_hex ?? null);
	const bound = $derived(whoami?.pubkey_hex ?? null);
	// true = local key matches the coordinator's binding; false = mismatch (rotated?);
	// null = can't compare yet.
	const matches = $derived(local && bound ? local === bound : null);
</script>

<h1>Overview</h1>
<p class="lead">
	Your local, tenant-scoped view of what your research is doing on the AuspexAI network.
</p>

{#if whoami?.suspended_at}
	<div class="suspended" role="alert">
		<strong>Your account is suspended.</strong>
		{#if whoami.suspension_reason}
			<span class="why">Reason: {whoami.suspension_reason}</span>
		{:else}
			<span class="why">No reason was recorded — contact the operator.</span>
		{/if}
		<span class="when">
			Suspended {whoami.suspended_at.slice(0, 10)}. Your workers are paused and new work is
			withheld until the suspension is lifted.
		</span>
	</div>
{/if}

{#if healthError}
	<p class="err">Could not reach the local backend: {healthError}</p>
{:else if !health}
	<p class="muted">Loading…</p>
{:else}
	<div class="grid">
		<div class="card">
			<h2>Identity</h2>
			{#if !health.identity.key_present}
				<p class="warn">No tenant key</p>
				<p class="muted">
					Run <code>auspexai-tenant key generate</code> once your tenant is approved.
				</p>
			{:else if whoami?.tenant_id}
				<p class="ok">Tenant <strong>{whoami.tenant_id}</strong></p>
				<p class="kv"><span>bound key</span><code title={bound ?? ''}>{short(bound)}</code></p>
				{#if matches === true}
					<p class="ok small">✓ local key matches the binding</p>
				{:else if matches === false}
					<p class="warn small">
						⚠ local key differs from the bound key — did you rotate it? Rebind via the operator
						console.
					</p>
				{/if}
			{:else if whoami}
				<!-- key present + recognized, but not a researcher tenant (e.g. anonymous/maintainer) -->
				<p class="warn">Recognized as <strong>{whoami.credential_class}</strong>, not a tenant</p>
			{:else if !whoamiError}
				<p class="muted">Confirming identity…</p>
			{/if}
			{#if health.identity.key_present}
				<p class="kv"><span>local key</span><code title={local ?? ''}>{short(local)}</code></p>
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
		<!-- SDK capability wedge (R-D inc-1): the dashboard monitors; the SDK is
		     the analysis + verification surface. Until docs live beyond the repo,
		     the README is the capability front door. -->
		<div class="card">
			<h2>Analysis &amp; verification</h2>
			<p class="muted">
				The dashboard monitors; the <code>auspexai-tenant</code> SDK is where your data
				becomes analyzable and provable:
			</p>
			<ul class="sdk-list">
				<li><code>experiment export --verify</code> — collect your evidence bundle, verified</li>
				<li><code>bundle verify</code> — re-verify it offline, forever</li>
				<li><code>bundle table</code> / <code>load_verified</code> — verified DataFrame, CSV, Parquet</li>
			</ul>
			<p class="muted">
				<a
					class="sdk-link"
					href="https://github.com/auspexai/tenant-sdk#readme"
					target="_blank"
					rel="noopener noreferrer"
				>Full capability map — SDK README ↗</a>
			</p>
		</div>
	</div>

	{#if whoamiError}
		<!-- Most importantly the unauthorized case: key present locally but the
		     coordinator has no tenant bound to it (unbound or rotated). -->
		<ErrorState error={whoamiError} />
	{/if}

	<p class="footer muted">{health.phase} · dashboard v{health.version}</p>
{/if}

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
	}
	.suspended {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		margin: 1rem 0;
		padding: 0.85rem 1rem;
		border: 1px solid #7f1d1d;
		border-left-width: 4px;
		border-radius: 6px;
		background: rgba(127, 29, 29, 0.18);
		color: #fca5a5;
	}
	.suspended strong {
		color: #fecaca;
		font-size: 0.95rem;
	}
	.suspended .why {
		color: #fca5a5;
	}
	.suspended .when {
		font-size: 0.8rem;
		color: #e7a3a3;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
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
	.small {
		font-size: 0.8rem;
	}
	.err {
		color: #fca5a5;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.kv {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.75rem;
		margin: 0.3rem 0;
		font-size: 0.8rem;
	}
	.kv span {
		color: #8b93a7;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		font-size: 0.68rem;
	}
	.kv code {
		font-family: ui-monospace, monospace;
		color: #b8bfd0;
	}
	.path {
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		color: #6b7390;
		word-break: break-all;
		margin-top: 0.5rem;
	}
	code {
		background: #1a2236;
		padding: 0.1rem 0.3rem;
		border-radius: 3px;
	}
	.footer {
		margin-top: 1.5rem;
	}
	.sdk-list {
		margin: 0.4rem 0;
		padding-left: 1.1rem;
		font-size: 0.8rem;
		color: #b8bfd0;
	}
	.sdk-list li {
		margin: 0.25rem 0;
	}
	a.sdk-link {
		color: #7aa2ff;
		text-decoration: none;
		font-size: 0.8rem;
	}
	a.sdk-link:hover {
		text-decoration: underline;
	}
</style>
