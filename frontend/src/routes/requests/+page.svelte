<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		ApiError,
		type CatalogEntry,
		type ModelRequest,
		type SoftwareRequest
	} from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';

	// R-D6 (§9 #46): the researcher's "push" surface. Signal demand the network
	// can't meet — a model nobody serves (data plane) or a worker-baseline
	// capability that doesn't exist (code plane) — and track each request
	// through assessment → resolution → the fulfilling release. 10s poll, no
	// SSE (the tenant-scoped stream is a later milestone).

	let modelRequests = $state<ModelRequest[]>([]);
	let softwareRequests = $state<SoftwareRequest[]>([]);
	let catalog = $state<CatalogEntry[]>([]);
	let loadError = $state<ApiError | null>(null);
	let loaded = $state(false);

	// submit form
	let kind = $state<'software' | 'model'>('software');
	let title = $state('');
	let description = $state('');
	let modelId = $state('');
	let hfRepo = $state('');
	let reason = $state('');
	let submitting = $state(false);
	let submitError = $state<string | null>(null);
	let submitOk = $state<string | null>(null);

	async function load(silent = false) {
		try {
			const [swr, mr, cat] = await Promise.all([
				api.listSoftwareRequests(),
				api.listModelRequests(),
				api.getCatalog()
			]);
			softwareRequests = swr.requests ?? [];
			modelRequests = mr.requests ?? [];
			catalog = cat.models ?? [];
			loadError = null;
		} catch (e) {
			if (!silent) loadError = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			loaded = true;
		}
	}

	const canSubmit = $derived(
		reason.trim().length > 0 &&
			(kind === 'software'
				? title.trim().length > 0 && description.trim().length > 0
				: modelId.trim().length > 0)
	);

	async function submit() {
		submitting = true;
		submitError = null;
		submitOk = null;
		try {
			if (kind === 'software') {
				const r = await api.createSoftwareRequest({
					title: title.trim(),
					description: description.trim(),
					reason: reason.trim()
				});
				submitOk = `submitted ${r.request_id} — queued for maintainer review (assessment → approve/decline → release).`;
				title = '';
				description = '';
			} else {
				const r = await api.createModelRequest({
					model_id: modelId.trim(),
					reason: reason.trim(),
					...(hfRepo.trim() ? { hf_repo: hfRepo.trim() } : {})
				});
				submitOk =
					r.status === 'available'
						? `submitted ${r.request_id} — the network already has a worker that can run this model.`
						: `submitted ${r.request_id} — no active worker holds it yet; queued for maintainer review.`;
				modelId = '';
				hfRepo = '';
			}
			reason = '';
			await load(true);
		} catch (e) {
			submitError = e instanceof ApiError ? e.message : String(e);
		} finally {
			submitting = false;
		}
	}

	onMount(() => {
		load();
		const t = setInterval(() => load(true), 10_000);
		return () => clearInterval(t);
	});
</script>

<svelte:head>
	<title>My Requests — AuspexAI</title>
</svelte:head>

<h1>My Requests</h1>
<p class="lead">
	Ask the network for what your experiments need: a <strong>model</strong> nobody serves yet, or a
	<strong>software capability</strong> the worker baseline doesn't provide. Software requests get a
	dependencies/security/alternatives assessment before the maintainer approves or declines; a worker
	release then fulfils approved requests.
</p>

{#if loadError}
	<ErrorState error={loadError} />
{:else if !loaded}
	<p class="muted">Loading…</p>
{:else}
	<section class="card">
		<h2>New request</h2>
		<div class="kind-row">
			<label class:checked={kind === 'software'}>
				<input type="radio" bind:group={kind} value="software" />
				software capability
			</label>
			<label class:checked={kind === 'model'}>
				<input type="radio" bind:group={kind} value="model" />
				model
			</label>
		</div>
		{#if kind === 'software'}
			<label>
				Title — short capability name
				<input bind:value={title} placeholder="e.g. Ollama inference serving" maxlength="200" />
			</label>
			<label>
				Description — what capability is needed
				<textarea bind:value={description} rows="3" maxlength="4000"></textarea>
			</label>
		{:else}
			<label>
				Model id — the worker store id (&lt;repo-slug&gt;-&lt;quant&gt;)
				<input bind:value={modelId} placeholder="e.g. gemma-3-1b-it-q4" maxlength="256" />
			</label>
			<label>
				HuggingFace repo hint (optional)
				<input bind:value={hfRepo} placeholder="e.g. google/gemma-3-1b-it-qat-q4_0-gguf" maxlength="256" />
			</label>
		{/if}
		<label>
			Why your experiments need it
			<textarea bind:value={reason} rows="2" maxlength="2000"></textarea>
		</label>
		<div class="submit-row">
			<button onclick={submit} disabled={submitting || !canSubmit}>
				{submitting ? 'submitting…' : 'submit request'}
			</button>
			{#if submitOk}<span class="ok-text">{submitOk}</span>{/if}
			{#if submitError}<span class="err-text">{submitError}</span>{/if}
		</div>
	</section>

	<section>
		<h2>Software requests</h2>
		{#if softwareRequests.length === 0}
			<p class="muted">None yet.</p>
		{:else}
			<table>
				<thead>
					<tr><th>title</th><th>status</th><th>assessment</th><th>resolution</th></tr>
				</thead>
				<tbody>
					{#each softwareRequests as r (r.request_id)}
						<tr>
							<td>
								<strong>{r.title}</strong>
								<div class="muted small">{r.request_id} · {new Date(r.created_at).toLocaleString()}</div>
							</td>
							<td>
								<StatusBadge status={r.status} />
								{#if r.release_version}
									<div class="muted small">released in v{r.release_version}</div>
								{/if}
							</td>
							<td class="assess">
								{#if r.assessment}
									{#if r.assessment_draft}<span class="draft">auto-draft (unreviewed)</span>{/if}
									<details>
										<summary>view</summary>
										<dl>
											<dt>dependencies</dt>
											<dd>{r.assessment.dependencies}</dd>
											<dt>security</dt>
											<dd>{r.assessment.security}</dd>
											<dt>alternatives</dt>
											<dd>{r.assessment.alternatives}</dd>
											{#if r.assessment.summary}<dt>summary</dt><dd>{r.assessment.summary}</dd>{/if}
										</dl>
									</details>
								{:else}
									<span class="muted">pending</span>
								{/if}
							</td>
							<td>
								{#if r.resolution_reason}
									<span class="muted">{r.resolved_by ?? '—'}: {r.resolution_reason}</span>
								{:else}
									<span class="muted">—</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</section>

	<section>
		<h2>Model requests</h2>
		{#if modelRequests.length === 0}
			<p class="muted">None yet.</p>
		{:else}
			<table>
				<thead>
					<tr><th>model</th><th>status</th><th>resolution</th></tr>
				</thead>
				<tbody>
					{#each modelRequests as r (r.request_id)}
						<tr>
							<td>
								<code>{r.model_id}</code>
								{#if r.hf_repo}<div class="muted small">{r.hf_repo}</div>{/if}
								<div class="muted small">{r.request_id} · {new Date(r.created_at).toLocaleString()}</div>
							</td>
							<td><StatusBadge status={r.status} /></td>
							<td>
								{#if r.resolution_reason}
									<span class="muted">{r.resolved_by ?? '—'}: {r.resolution_reason}</span>
								{:else}
									<span class="muted">—</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</section>

	<section>
		<h2>Network model catalog</h2>
		<p class="muted">What active workers can run right now — check before requesting a model.</p>
		{#if catalog.length === 0}
			<p class="muted">No models on the network yet.</p>
		{:else}
			<table>
				<thead><tr><th>model id</th><th>workers</th></tr></thead>
				<tbody>
					{#each catalog as m (m.model_id)}
						<tr><td><code>{m.model_id}</code></td><td>{m.worker_count}</td></tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</section>
{/if}

<style>
	h1 {
		margin-bottom: 0.25rem;
	}
	.lead {
		color: #8b93a7;
		max-width: 60rem;
	}
	section {
		margin-top: 1.75rem;
	}
	.card {
		background: #10182a;
		border: 1px solid #1e2638;
		border-radius: 8px;
		padding: 1rem 1.25rem 1.25rem;
		max-width: 44rem;
	}
	h2 {
		font-size: 1.05rem;
		margin: 0 0 0.5rem;
	}
	.kind-row {
		display: flex;
		gap: 0.75rem;
		margin-bottom: 0.5rem;
	}
	.kind-row label {
		display: flex;
		gap: 0.4rem;
		align-items: center;
		padding: 0.3rem 0.7rem;
		border: 1px solid #2a3450;
		border-radius: 6px;
		cursor: pointer;
		color: #b8bfd0;
		font-size: 0.9rem;
	}
	.kind-row label.checked {
		border-color: #67e8f9;
		color: #e2e8f0;
	}
	label {
		display: block;
		margin: 0.6rem 0 0.2rem;
		color: #8b93a7;
		font-size: 0.88rem;
	}
	input:not([type='radio']),
	textarea {
		width: 100%;
		box-sizing: border-box;
		background: #0a1020;
		color: #e2e8f0;
		border: 1px solid #2a3450;
		border-radius: 6px;
		padding: 0.45rem 0.6rem;
		font: inherit;
		margin-top: 0.25rem;
	}
	.submit-row {
		margin-top: 0.9rem;
		display: flex;
		gap: 0.75rem;
		align-items: baseline;
		flex-wrap: wrap;
	}
	button {
		background: #155e6b;
		color: #e0fbff;
		border: 1px solid #1d7f90;
		border-radius: 6px;
		padding: 0.45rem 1rem;
		font: inherit;
		cursor: pointer;
	}
	button:disabled {
		opacity: 0.5;
		cursor: default;
	}
	.ok-text {
		color: #6ee7b7;
		font-size: 0.88rem;
	}
	.err-text {
		color: #fca5a5;
		font-size: 0.88rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9rem;
	}
	th {
		text-align: left;
		color: #8b93a7;
		font-weight: 500;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #2a3450;
	}
	td {
		padding: 0.5rem 0.6rem;
		border-bottom: 1px solid #1e2638;
		vertical-align: top;
	}
	.muted {
		color: #5d6578;
	}
	.small {
		font-size: 0.78rem;
	}
	.assess {
		max-width: 24rem;
	}
	.assess .draft {
		color: #fbbf24;
		font-size: 0.8rem;
		display: block;
		margin-bottom: 0.2rem;
	}
	.assess details summary {
		cursor: pointer;
		color: #93c5fd;
		font-size: 0.85rem;
	}
	.assess dl {
		margin: 0.4rem 0 0;
		font-size: 0.85rem;
	}
	.assess dt {
		color: #8b93a7;
		font-weight: 600;
		margin-top: 0.35rem;
	}
	.assess dd {
		margin: 0.1rem 0 0;
		white-space: pre-wrap;
	}
	code {
		background: #0a1020;
		padding: 0.1rem 0.35rem;
		border-radius: 4px;
		font-size: 0.85em;
	}
</style>
