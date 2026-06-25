<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { api, ApiError } from '$lib/api';

	// Tier-1 onboarding: CONNECT your account (ORCID or GitHub) — no form, no
	// approval, like a worker connecting. ORCID uses client-side implicit OAuth
	// (token in the URL fragment); GitHub uses the device flow brokered by the
	// local backend. Either token is handed to the coordinator via the local-key-
	// signed POST /accounts/bind, which binds this dashboard's key to an account.
	// Connecting done → straight to Run Experiment (the certified Vigiles starter
	// runs under its public tenant; create your OWN tenant later if you bring code).
	const ORCID_AUTHORIZE = 'https://orcid.org/oauth/authorize';
	const ORCID_CLIENT_ID = 'APP-68HHEVY8P8XLYO05'; // public by design

	let phase = $state<'choose' | 'binding' | 'github' | 'done'>('choose');
	let error = $state<string | null>(null);
	let gh = $state<{ user_code: string; verification_uri: string } | null>(null);
	let pollTimer: ReturnType<typeof setInterval> | null = null;

	function connectOrcid() {
		error = null;
		const state = crypto.randomUUID();
		sessionStorage.setItem('orcid_connect_state', state);
		const redirect = `${window.location.origin}/onboard`;
		window.location.href =
			`${ORCID_AUTHORIZE}?client_id=${ORCID_CLIENT_ID}&response_type=token&scope=openid` +
			`&redirect_uri=${encodeURIComponent(redirect)}&state=${encodeURIComponent(state)}`;
	}

	async function bind(idp: 'orcid' | 'github', accessToken: string) {
		phase = 'binding';
		try {
			await api.bindAccount({ idp, access_token: accessToken });
			phase = 'done';
			// Hard nav so the dashboard re-fetches whoami (now an onboarded account)
			// and lands on Run Experiment.
			setTimeout(() => (window.location.href = '/run'), 700);
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
			phase = 'choose';
		}
	}

	async function connectGithub() {
		error = null;
		phase = 'github';
		try {
			const start = await api.githubDeviceStart();
			gh = { user_code: start.user_code, verification_uri: start.verification_uri };
			const interval = Math.max(5, start.interval || 5) * 1000;
			pollTimer = setInterval(async () => {
				try {
					const r = await api.githubDevicePoll(start.device_code);
					if (r.access_token) {
						if (pollTimer) clearInterval(pollTimer);
						await bind('github', r.access_token);
					} else if (r.error && r.error !== 'authorization_pending' && r.error !== 'slow_down') {
						if (pollTimer) clearInterval(pollTimer);
						error = `GitHub sign-in failed (${r.error}).`;
						phase = 'choose';
					}
				} catch (e) {
					if (pollTimer) clearInterval(pollTimer);
					error = e instanceof ApiError ? e.message : String(e);
					phase = 'choose';
				}
			}, interval);
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
			phase = 'choose';
		}
	}

	onDestroy(() => {
		if (pollTimer) clearInterval(pollTimer);
	});

	onMount(() => {
		// ORCID implicit returns #access_token=...&state=... in the fragment.
		const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
		if (!raw) return;
		const params = new URLSearchParams(raw);
		const accessToken = params.get('access_token');
		const returnedState = params.get('state');
		const orcidError = params.get('error');
		history.replaceState(null, '', window.location.pathname); // never leave the token in the bar
		if (orcidError) {
			error = `ORCID sign-in was cancelled or failed (${orcidError}).`;
			return;
		}
		if (!accessToken) return;
		const expected = sessionStorage.getItem('orcid_connect_state');
		sessionStorage.removeItem('orcid_connect_state');
		if (!expected || returnedState !== expected) {
			error = 'ORCID sign-in could not be verified (state mismatch). Please try again.';
			return;
		}
		bind('orcid', accessToken);
	});
</script>

<svelte:head><title>Connect your account — AuspexAI</title></svelte:head>

<h1>Connect your account</h1>
<p class="lead">
	Connect with <strong>ORCID</strong> or <strong>GitHub</strong> to start — no forms, no waiting.
	You can run the certified <strong>Vigiles</strong> starter right away; create your own tenant
	later if you bring your own code.
</p>

{#if phase === 'binding'}
	<p class="muted">Connecting…</p>
{:else if phase === 'done'}
	<p class="ok">Connected ✓ — taking you to Run Experiment…</p>
{:else if phase === 'github' && gh}
	<div class="card">
		<h2>Finish on GitHub</h2>
		<p>
			Open
			<a href={gh.verification_uri} target="_blank" rel="noopener noreferrer"
				>{gh.verification_uri} ↗</a
			>
			and enter this code:
		</p>
		<p class="code">{gh.user_code}</p>
		<p class="muted small">Waiting for you to authorize on GitHub…</p>
	</div>
{:else}
	{#if error}<p class="error">{error}</p>{/if}
	<div class="cta-row">
		<button class="orcid-btn" onclick={connectOrcid}>Connect with ORCID</button>
		<button class="gh-btn" onclick={connectGithub}>Connect with GitHub</button>
	</div>
	<p class="muted small">
		ORCID verifies your academic identity, so you start eligible for higher research standing.
		GitHub is the dev-identity path. Either way: connect → run.
	</p>
{/if}

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
		max-width: 60ch;
	}
	.cta-row {
		display: flex;
		gap: 0.8rem;
		flex-wrap: wrap;
		margin: 1.25rem 0 0.6rem;
	}
	.orcid-btn,
	.gh-btn {
		border: none;
		border-radius: 6px;
		padding: 0.6rem 1.2rem;
		font-weight: 700;
		font-size: 0.95rem;
		cursor: pointer;
	}
	.orcid-btn {
		background: #a6ce39;
		color: #1a2000;
	}
	.gh-btn {
		background: #24292f;
		color: #fff;
		border: 1px solid #444c56;
	}
	.orcid-btn:hover {
		background: #b4d94f;
	}
	.gh-btn:hover {
		background: #2d333b;
	}
	.card {
		border: 1px solid #1d7f90;
		border-left-width: 4px;
		border-radius: 8px;
		background: linear-gradient(180deg, rgba(21, 94, 107, 0.18), #10182a);
		padding: 1rem 1.25rem;
		margin-top: 1rem;
		max-width: 52ch;
	}
	.card h2 {
		margin: 0 0 0.4rem;
		font-size: 1.05rem;
		color: #e0fbff;
	}
	.code {
		font-family: ui-monospace, monospace;
		font-size: 1.6rem;
		letter-spacing: 0.18em;
		color: #67e8f9;
		margin: 0.4rem 0;
	}
	.ok {
		color: #6ee7b7;
		font-weight: 600;
	}
	.error {
		color: #fca5a5;
		font-size: 0.9rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.small {
		font-size: 0.8rem;
		max-width: 60ch;
	}
	a {
		color: #7aa2ff;
	}
</style>
