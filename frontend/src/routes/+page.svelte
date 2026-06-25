<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError, type TenantApplication, type WhoAmI } from '$lib/api';
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
	// Onboarding tracker (key present but not bound): null = not fetched yet.
	let applications = $state<TenantApplication[] | null>(null);
	let applicationsError = $state<string | null>(null);
	// D8 ORCID linking.
	let orcidLinking = $state(false);
	let orcidNote = $state<string | null>(null);

	const ONBOARDING_URL = 'https://github.com/auspexai/.github/blob/main/ONBOARDING.md';

	// pubkeys are 64 hex chars; show head…tail, full string on hover.
	const short = (k: string | null | undefined) => (k ? `${k.slice(0, 10)}…${k.slice(-8)}` : '—');

	// D8: send the researcher to ORCID; the coordinator callback returns here.
	async function linkOrcid() {
		orcidLinking = true;
		orcidNote = null;
		try {
			const { authorize_url } = await api.linkOrcidStart();
			window.location.href = authorize_url;
		} catch (e) {
			orcidNote = `Couldn't start ORCID linking: ${e instanceof ApiError ? e.message : String(e)}`;
			orcidLinking = false;
		}
	}

	onMount(async () => {
		// The ORCID callback bounces back here with ?orcid=linked|error|expired.
		const r = new URLSearchParams(window.location.search).get('orcid');
		if (r === 'linked') orcidNote = 'ORCID linked ✓';
		else if (r === 'expired') orcidNote = 'ORCID link expired — please try again.';
		else if (r === 'error') orcidNote = 'ORCID linking failed — please try again.';
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
				// Key present but not bound → applicant territory: ask the
				// coordinator for this key's applications. That route works for an
				// unregistered key (self-keyid proof of possession), so it is
				// exactly the state where whoami fails that it exists for.
				if (whoamiError.kind === 'unauthorized') {
					try {
						applications = (await api.listMyApplications()).applications ?? [];
					} catch (e2) {
						applicationsError = e2 instanceof ApiError ? e2.message : String(e2);
					}
				}
			}
		}
	});

	const local = $derived(health?.identity.pubkey_hex ?? null);
	const bound = $derived(whoami?.pubkey_hex ?? null);
	// true = local key matches the coordinator's binding; false = mismatch (rotated?);
	// null = can't compare yet.
	const matches = $derived(local && bound ? local === bound : null);

	// Onboarding tracker: a pending application wins; otherwise the newest one
	// decides (the coordinator returns them newest-first).
	const pendingApp = $derived(applications?.find((a) => a.status === 'pending') ?? null);
	const newestApp = $derived(applications?.[0] ?? null);
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
					Run <code>auspexai-tenant apply</code> — it creates your key and submits your
					application.
				</p>
				<p class="muted">
					<a class="doc-link" href={ONBOARDING_URL} target="_blank" rel="noopener noreferrer"
						>Onboarding guide ↗</a
					>
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
				{#if whoami.research_standing !== undefined && whoami.research_standing !== null}
					{@const r = whoami.research_standing}
					{@const rLabel =
						['R0 · unverified', 'R1 · verified', 'R2 · established', 'R3 · trusted'][r] ??
						`R${r}`}
					<p class="kv"><span>research standing</span><strong>{rLabel}</strong></p>
					{#if r === 1}
						{#if whoami.research_standing_eligible_for_r2}
							<p class="ok small">
								✓ eligible for the R2 review — {whoami.research_standing_distinct}
								distinct experiments (a maintainer promotes)
							</p>
						{:else}
							<p class="muted small">
								{whoami.research_standing_distinct ?? 0} of {whoami.research_standing_threshold ?? 3}
								distinct, completed, attested experiments toward the R2 review
							</p>
						{/if}
					{/if}
				{/if}
				{#if whoami.orcid_id}
					<p class="kv">
						<span>orcid</span>
						<a
							class="orcid"
							href="https://orcid.org/{whoami.orcid_id}"
							target="_blank"
							rel="noopener noreferrer">{whoami.orcid_id} ↗</a
						>
					</p>
				{:else}
					<div class="orcid-link">
						<button class="orcid-btn" onclick={linkOrcid} disabled={orcidLinking}>
							{orcidLinking ? 'Opening ORCID…' : 'Link ORCID'}
						</button>
						<span class="muted small">verifies your researcher identity (for R3)</span>
					</div>
				{/if}
				{#if orcidNote}<p class="ok small">{orcidNote}</p>{/if}
			{:else if whoami}
				<!-- key present + recognized, but not a researcher tenant (e.g. anonymous/maintainer) -->
				{#if whoami.credential_class === 'account'}<p class="ok">Connected ✓ — run the <a href="/run">Vigiles starter</a>, or create your own tenant when you bring code.</p>{:else}<p class="warn">Recognized as <strong>{whoami.credential_class}</strong>, not a tenant</p>{/if}
			{:else if whoamiError?.kind === 'unauthorized'}
				<!-- Key present but the coordinator has no tenant bound to it:
				     applicant territory, not an operator problem. Track the
				     application this key submitted instead (the /mine route works
				     for an unregistered key — self-keyid proof of possession). -->
				{#if applicationsError}
					<p class="warn">Key not bound to a tenant yet</p>
					<p class="muted">Could not check your application status: {applicationsError}</p>
				{:else if applications === null}
					<p class="muted">Key not bound yet — checking for your application…</p>
				{:else if pendingApp}
					<p class="warn">
						Application <code>{pendingApp.application_id}</code> pending Maintainer review
					</p>
					<p class="muted small">This page goes green on approval.</p>
				{:else if newestApp?.status === 'declined'}
					<p class="warn">Application <code>{newestApp.application_id}</code> declined</p>
					{#if newestApp.resolution_reason}
						<p class="muted">Reason: {newestApp.resolution_reason}</p>
					{/if}
					<p class="muted small">You can <a class="apply-link" href="/onboard">connect a different account →</a></p>
				{:else if newestApp}
					<!-- Unexpected: newest application is approved yet whoami still says
					     unbound (approval seconds ago, or the key changed since). -->
					<p class="warn">
						Application <code>{newestApp.application_id}</code> approved, but this key isn't
						bound yet
					</p>
					<p class="muted small">Reload in a moment; if it persists, contact the Maintainer.</p>
				{:else}
					<p class="warn">Not connected yet</p>
					<p class="muted"><a class="apply-link" href="/onboard">Connect your account →</a> (GitHub or ORCID)</p>
					<p class="muted">
						<a class="doc-link" href={ONBOARDING_URL} target="_blank" rel="noopener noreferrer"
							>Onboarding guide ↗</a
						>
					</p>
				{/if}
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
	</div>

	{#if whoamiError && whoamiError.kind !== 'unauthorized'}
		<!-- Transport/coordinator failures only. The unauthorized case (key
		     present but not bound) is an applicant state, rendered as the
		     onboarding tracker in the Identity card above — not as an error. -->
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
	a.orcid {
		font-family: ui-monospace, monospace;
		color: #a6ce39; /* ORCID green */
		text-decoration: none;
	}
	a.orcid:hover {
		text-decoration: underline;
	}
	.orcid-link {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin: 0.4rem 0 0.2rem;
		flex-wrap: wrap;
	}
	.orcid-btn {
		background: #16203a;
		color: #cdd5e6;
		border: 1px solid #2a3450;
		border-radius: 6px;
		padding: 0.3rem 0.7rem;
		font: inherit;
		font-size: 0.8rem;
		cursor: pointer;
	}
	.orcid-btn:hover:not(:disabled) {
		border-color: #a6ce39;
	}
	.orcid-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
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
	a.doc-link {
		color: #7aa2ff;
		text-decoration: none;
		font-size: 0.8rem;
	}
	a.doc-link:hover {
		text-decoration: underline;
	}
	a.apply-link {
		color: #a6ce39;
		font-weight: 600;
		text-decoration: none;
	}
	a.apply-link:hover {
		text-decoration: underline;
	}
</style>
