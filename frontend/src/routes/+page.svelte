<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		ApiError,
		type AccountWorker,
		type TenantApplication,
		type WhoAmI
	} from '$lib/api';
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
	// Account-scoped worker liveness for the "Your workers" panel (only the
	// caller's own-account workers; the coordinator strips everyone else).
	let workers = $state<AccountWorker[] | null>(null);
	// D8 ORCID linking.
	let orcidLinking = $state(false);
	let orcidNote = $state<string | null>(null);

	const ONBOARDING_URL = 'https://github.com/auspexai/.github/blob/main/ONBOARDING.md';

	// pubkeys are 64 hex chars; show head…tail, full string on hover.
	const short = (k: string | null | undefined) => (k ? `${k.slice(0, 10)}…${k.slice(-8)}` : '—');

	// Compact relative time for a heartbeat ("12s ago" / "3h ago").
	function ago(iso: string | null | undefined): string {
		if (!iso) return 'never';
		const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
		if (s < 60) return `${s}s ago`;
		const m = Math.round(s / 60);
		if (m < 60) return `${m}m ago`;
		const h = Math.round(m / 60);
		if (h < 24) return `${h}h ago`;
		return `${Math.round(h / 24)}d ago`;
	}

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
				// Connected → load this account's workers for the liveness panel. A
				// failure here is non-fatal: the panel just stays empty.
				try {
					workers = (await api.myWorkers()).workers ?? [];
				} catch {
					workers = [];
				}
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

	// A recognized researcher tenant OR a connected account — both render the one
	// unified account-identity view (identity = the account; an operated tenant is
	// a *workspace*, shown as a secondary line, not as identity).
	const connected = $derived(
		!!whoami && (!!whoami.tenant_id || whoami.credential_class === 'account')
	);
	// The verified GitHub handle, only for a github-rooted account (display_name is
	// the OAuth login). An orcid-rooted account shows ORCID as its root instead.
	const githubLogin = $derived(
		whoami?.idp === 'github' && whoami?.display_name ? whoami.display_name : null
	);

	// Onboarding tracker: a pending application wins; otherwise the newest one
	// decides (the coordinator returns them newest-first).
	const pendingApp = $derived(applications?.find((a) => a.status === 'pending') ?? null);
	const newestApp = $derived(applications?.[0] ?? null);

	const onlineCount = $derived((workers ?? []).filter((w) => w.status === 'active').length);
	const offlineCount = $derived((workers ?? []).filter((w) => w.status !== 'active').length);
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
			{:else if whoami && (whoami.tenant_id || whoami.credential_class === 'account')}
				<!-- Unified account identity: GitHub + ORCID + standing + key + workspace.
				     Identity = the account; the tenant is demoted to a workspace line. -->
				{#if githubLogin}
					<p class="kv">
						<span>github</span>
						<a
							class="gh"
							href="https://github.com/{githubLogin}"
							target="_blank"
							rel="noopener noreferrer">{githubLogin} ↗</a
						>
					</p>
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
				<!-- Consolidated signing key: one line + a ✓ bound chip in the common
				     case; fan out to bound-vs-local only when they actually differ. -->
				{#if matches === false}
					<p class="kv"><span>bound key</span><code title={bound ?? ''}>{short(bound)}</code></p>
					<p class="kv"><span>local key</span><code title={local ?? ''}>{short(local)}</code></p>
					<p class="warn small">
						⚠ local key differs from the bound key — did you rotate it? Rebind via the operator
						console.
					</p>
				{:else}
					<p class="kv">
						<span>key</span>
						<code title={bound ?? local ?? ''}
							>{short(bound ?? local)} <span class="chip">✓ bound</span></code
						>
					</p>
				{/if}
				{#if !whoami.orcid_id}
					<div class="orcid-link">
						<button class="orcid-btn" onclick={linkOrcid} disabled={orcidLinking}>
							{orcidLinking ? 'Opening ORCID…' : 'Link ORCID'}
						</button>
						<span class="muted small">verifies your researcher identity (for R3)</span>
					</div>
				{/if}
				{#if orcidNote}<p class="ok small">{orcidNote}</p>{/if}
				<!-- The operated tenant as a workspace (not identity); a connected
				     account with no tenant is a member of every certified tenant. -->
				{#if whoami.tenant_id}
					<p class="kv">
						<span>workspace</span><a class="apply-link" href="/run">{whoami.tenant_id} →</a>
					</p>
				{:else}
					<p class="muted small">
						Member of every certified tenant — <a class="apply-link" href="/run"
							>run the Vigiles starter →</a
						> or create your own tenant when you bring code.
					</p>
				{/if}
			{:else if whoami}
				<!-- key present + recognized, but not a researcher tenant or account
				     (e.g. anonymous/maintainer) -->
				<p class="warn">Recognized as <strong>{whoami.credential_class}</strong>, not a tenant</p>
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
					<p class="muted small">
						You can <a class="apply-link" href="/onboard">connect a different account →</a>
					</p>
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
			{#if health.identity.key_present && !connected}
				<p class="kv"><span>local key</span><code title={local ?? ''}>{short(local)}</code></p>
			{/if}
			<p class="path">{health.identity.key_path}</p>
		</div>
		<div class="card">
			<h2>Connection</h2>
			<p class="kv"><span>backend</span><span class="ok">✓ reachable</span></p>
			<p class="kv">
				<span>coordinator</span>
				{#if health.coord.reachable}
					<span class="ok" title={health.coord.url}>✓ reachable</span>
				{:else}
					<span class="bad">✗ unreachable</span>
				{/if}
			</p>
			{#if workers && workers.length > 0}
				<p class="kv">
					<span>workers</span>
					<span
						><span class="ok">{onlineCount} online</span>{#if offlineCount}&nbsp;· {offlineCount}
							offline{/if}</span
					>
				</p>
			{:else if connected}
				<p class="kv"><span>workers</span><span class="muted">none bound</span></p>
			{/if}
			<!-- The coordinator URL + status detail are diagnostic: shown only when
			     UNREACHABLE (then they're actionable — which endpoint, what error). In
			     the healthy path the URL lives on the row's hover title, and the "ok"
			     detail is dropped (it only ever duplicated ✓ reachable). -->
			{#if !health.coord.reachable}
				<p class="coord-error">
					{health.coord.url}{#if health.coord.detail} · {health.coord.detail}{/if}
				</p>
			{/if}
		</div>
	</div>

	{#if workers && workers.length > 0}
		<div class="workers-card">
			<h2>Your workers</h2>
			<p class="muted">
				Compute bound to your account, with live status. A logged-out worker drops off here; its
				past contributions stay credited (and show on each experiment it backed).
			</p>
			<table class="workers">
				<thead>
					<tr><th>Worker</th><th>Tier</th><th>Status</th><th>Last heartbeat</th><th>Results</th></tr>
				</thead>
				<tbody>
					{#each workers as w (w.worker_id)}
						<tr>
							<td>
								<span class="wid">{w.worker_id}</span>
								<span class="mono pk">{w.pubkey_hex.slice(0, 16)}…</span>
							</td>
							<td>T{w.trust_tier}</td>
							<td>
								<span class="wstatus s-{w.status}">{w.status}</span>
								{#if w.status === 'quarantined' && w.quarantine_reason}
									<div class="reason" title="The maintainer's reason.">{w.quarantine_reason}</div>
								{/if}
							</td>
							<td class="muted">{ago(w.last_heartbeat_at)}</td>
							<td>{w.result_count}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}

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
	.card h2,
	.workers-card h2 {
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
	.bad {
		color: #fca5a5; /* red — a fault / failure state */
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
	a.gh {
		font-family: ui-monospace, monospace;
		color: #adbac7;
		text-decoration: none;
	}
	a.gh:hover {
		text-decoration: underline;
	}
	.chip {
		color: #6ee7b7;
		font-size: 0.7rem;
		font-family: system-ui, sans-serif;
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
	.coord-error {
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		color: #fca5a5; /* red — the failing endpoint + reason, shown only when down */
		word-break: break-all;
		margin-top: 0.4rem;
	}
	code {
		background: #1a2236;
		padding: 0.1rem 0.3rem;
		border-radius: 3px;
	}
	.workers-card {
		border: 1px solid #1e2638;
		border-radius: 8px;
		padding: 1rem 1.25rem;
		background: #0e1424;
		margin-top: 1rem;
	}
	table.workers {
		width: 100%;
		border-collapse: collapse;
		margin-top: 0.5rem;
		font-size: 0.82rem;
	}
	table.workers th {
		text-align: left;
		color: #8b93a7;
		font-weight: 600;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 0.3rem 0.6rem;
		border-bottom: 1px solid #1e2638;
	}
	table.workers td {
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #161d2e;
		color: #b8bfd0;
		vertical-align: top;
	}
	.wid {
		color: #cdd5e6;
	}
	.mono {
		font-family: ui-monospace, monospace;
	}
	.pk {
		color: #6b7390;
		font-size: 0.72rem;
	}
	.wstatus {
		font-size: 0.72rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding: 0.1rem 0.4rem;
		border-radius: 4px;
	}
	.s-active {
		color: #6ee7b7;
		background: rgba(110, 231, 183, 0.12);
	}
	.s-offline {
		color: #8b93a7;
		background: rgba(139, 147, 167, 0.12);
	}
	.s-quarantined {
		color: #fca5a5; /* red — a fault state */
		background: rgba(248, 113, 113, 0.14);
	}
	.s-retired {
		color: #6b7390;
		background: rgba(107, 115, 144, 0.12);
	}
	.reason {
		color: #e7a3a3;
		font-size: 0.72rem;
		margin-top: 0.15rem;
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
