<script lang="ts">
	import { onMount } from 'svelte';
	import { api, ApiError } from '$lib/api';

	// ORCID-rooted onboarding (#16). The researcher fills the application, then
	// "Continue with ORCID" runs ORCID's client-side implicit OAuth
	// (response_type=token, scope=openid). ORCID redirects back here with the
	// access token in the URL fragment; we hand that token + the stashed form to
	// the coordinator (via the local-key-signed backend), which verifies the
	// token through ORCID userinfo, roots the account on ORCID, and creates the
	// pending application. No secret in the browser; the token is read from the
	// fragment client-side and sent once over the local signed POST.
	const ORCID_AUTHORIZE = 'https://orcid.org/oauth/authorize';
	const ORCID_CLIENT_ID = 'APP-68HHEVY8P8XLYO05'; // public by design

	let form = $state({
		requested_tenant_id: '',
		contact_name: '',
		affiliation: '',
		research_summary: ''
	});
	let phase = $state<'form' | 'returning' | 'done'>('form');
	let submitting = $state(false);
	let error = $state<string | null>(null);
	let result = $state<{ application_id: string; status: string } | null>(null);

	const valid = $derived(
		form.requested_tenant_id.trim().length > 0 &&
			form.contact_name.trim().length > 0 &&
			form.affiliation.trim().length > 0 &&
			form.research_summary.trim().length > 0
	);

	function continueWithOrcid() {
		error = null;
		if (!valid) {
			error = 'Tenant id, contact name, affiliation, and a short research summary are all required.';
			return;
		}
		const state = crypto.randomUUID();
		sessionStorage.setItem('orcid_apply_state', state);
		sessionStorage.setItem('orcid_apply_form', JSON.stringify(form));
		const redirect = `${window.location.origin}/onboard`;
		window.location.href =
			`${ORCID_AUTHORIZE}?client_id=${ORCID_CLIENT_ID}` +
			`&response_type=token&scope=openid` +
			`&redirect_uri=${encodeURIComponent(redirect)}` +
			`&state=${encodeURIComponent(state)}`;
	}

	async function submitApply(accessToken: string, saved: typeof form) {
		submitting = true;
		try {
			result = await api.applyTenant({
				orcid_access_token: accessToken,
				requested_tenant_id: saved.requested_tenant_id.trim(),
				contact_name: saved.contact_name.trim(),
				affiliation: saved.affiliation.trim(),
				research_summary: saved.research_summary.trim() || undefined
			});
			phase = 'done';
		} catch (e) {
			error = e instanceof ApiError ? e.message : String(e);
			phase = 'form';
		} finally {
			submitting = false;
		}
	}

	onMount(() => {
		const raw = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
		if (!raw) return;
		const params = new URLSearchParams(raw);
		const accessToken = params.get('access_token');
		const returnedState = params.get('state');
		const orcidError = params.get('error');
		// Strip the fragment immediately — never leave the token in the address bar.
		history.replaceState(null, '', window.location.pathname);
		if (orcidError) {
			error = `ORCID sign-in was cancelled or failed (${orcidError}).`;
			return;
		}
		if (!accessToken) return;
		phase = 'returning';
		const expected = sessionStorage.getItem('orcid_apply_state');
		const savedRaw = sessionStorage.getItem('orcid_apply_form');
		sessionStorage.removeItem('orcid_apply_state');
		sessionStorage.removeItem('orcid_apply_form');
		if (!expected || returnedState !== expected) {
			error = 'ORCID sign-in could not be verified (state mismatch). Please start again.';
			phase = 'form';
			return;
		}
		if (!savedRaw) {
			error = 'Your application details were lost in the round-trip. Please re-enter them.';
			phase = 'form';
			return;
		}
		const saved = JSON.parse(savedRaw);
		form = saved;
		submitApply(accessToken, saved);
	});
</script>

<svelte:head><title>Apply with ORCID — AuspexAI</title></svelte:head>

<h1>Apply as a researcher</h1>
<p class="lead">
	Root your tenant on <strong>ORCID</strong> — your academic identity is verified at sign-in, so you
	start eligible for higher research standing. A maintainer reviews every application.
</p>

{#if phase === 'returning'}
	<p class="muted">Verifying your ORCID and submitting…</p>
{:else if phase === 'done' && result}
	<div class="done">
		<h2>Application submitted ✓</h2>
		<p>
			<code>{result.application_id}</code> is <strong>{result.status}</strong>, pending maintainer
			review. This dashboard goes live once it's approved.
		</p>
		<p class="muted">Track it on the <a href="/">overview</a>.</p>
	</div>
{:else}
	<form
		onsubmit={(e) => {
			e.preventDefault();
			continueWithOrcid();
		}}
	>
		<label>
			Tenant id <span class="req">*</span>
			<input bind:value={form.requested_tenant_id} placeholder="e.g. my-lab" maxlength="64" />
			<span class="hint">your tenant's handle on the network</span>
		</label>
		<label>
			Contact name <span class="req">*</span>
			<input bind:value={form.contact_name} placeholder="e.g. Ada Lovelace" maxlength="200" />
		</label>
		<label>
			Affiliation <span class="req">*</span>
			<input
				bind:value={form.affiliation}
				placeholder="e.g. Independent — drift research"
				maxlength="200"
			/>
		</label>
		<label>
			Research summary <span class="req">*</span>
			<textarea
				bind:value={form.research_summary}
				rows="3"
				maxlength="4000"
				placeholder="What will you run on the network?"
			></textarea>
		</label>
		{#if error}<p class="error">{error}</p>{/if}
		<button class="orcid-btn" type="submit" disabled={submitting || !valid}>
			{submitting ? 'Submitting…' : 'Continue with ORCID →'}
		</button>
		<p class="muted small">
			Prefer GitHub? Run <code>auspexai-tenant apply</code> from the SDK instead.
		</p>
	</form>
{/if}

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
		max-width: 60ch;
	}
	form {
		display: flex;
		flex-direction: column;
		gap: 0.9rem;
		max-width: 46ch;
		margin-top: 1.25rem;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		font-size: 0.9rem;
		color: #cdd5e6;
	}
	.req {
		color: #f59e0b;
	}
	input,
	textarea {
		background: #0d1119;
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.5rem 0.6rem;
		color: #e6e9f0;
		font: inherit;
		font-size: 0.9rem;
	}
	input:focus,
	textarea:focus {
		outline: none;
		border-color: #67e8f9;
	}
	.hint {
		color: #8b93a7;
		font-size: 0.78rem;
	}
	.orcid-btn {
		align-self: flex-start;
		background: #a6ce39;
		color: #1a2000;
		border: none;
		border-radius: 6px;
		padding: 0.55rem 1.1rem;
		font-weight: 700;
		font-size: 0.9rem;
		cursor: pointer;
	}
	.orcid-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.error {
		color: #fca5a5;
		font-size: 0.85rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.small {
		font-size: 0.8rem;
	}
	.done {
		border: 1px solid #1f5d4a;
		border-left-width: 4px;
		border-radius: 8px;
		background: rgba(21, 94, 75, 0.18);
		padding: 1rem 1.25rem;
		margin-top: 1rem;
		max-width: 60ch;
	}
	.done h2 {
		margin: 0 0 0.4rem;
		color: #6ee7b7;
		font-size: 1.1rem;
	}
	code {
		background: #0d1119;
		padding: 0.05em 0.35em;
		border-radius: 3px;
		font-size: 0.88em;
	}
	a {
		color: #7aa2ff;
	}
</style>
