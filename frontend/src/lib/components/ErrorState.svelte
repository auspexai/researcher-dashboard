<script lang="ts">
	import type { ApiError } from '$lib/api';

	let { error }: { error: ApiError } = $props();

	const titles: Record<string, string> = {
		no_identity: 'No tenant key',
		unauthorized: 'Tenant key not recognized',
		unreachable: 'Backend unreachable',
		not_found: 'Not found',
		coordinator_error: 'Coordinator error',
		client_error: 'Something went wrong'
	};

	// no_identity / unauthorized are recoverable setup states (amber), the rest
	// are failures (red).
	const isSetup = $derived(error.kind === 'no_identity' || error.kind === 'unauthorized');
</script>

<div class="error" class:setup={isSetup}>
	<h2>{titles[error.kind] ?? 'Error'}</h2>
	<p>{error.message}</p>
	{#if error.kind === 'unauthorized'}
		<p class="hint">
			The coordinator has no tenant bound to this key. If you rotated it, rebind the new public
			key via the operator console, then reload.
		</p>
	{:else if error.kind === 'no_identity'}
		<p class="hint">
			Generate one with <code>auspexai-tenant key generate</code> once your tenant is approved.
		</p>
	{/if}
</div>

<style>
	.error {
		border: 1px solid #3a2230;
		border-left: 3px solid #fca5a5;
		border-radius: 8px;
		padding: 1rem 1.25rem;
		background: #160f16;
		margin-top: 1rem;
	}
	.error.setup {
		border-color: #3a3322;
		border-left-color: #fbbf24;
		background: #14110a;
	}
	h2 {
		font-size: 0.95rem;
		margin: 0 0 0.4rem;
		color: #f1f3f8;
	}
	p {
		color: #c8cdda;
		margin: 0.25rem 0;
		font-size: 0.9rem;
	}
	.hint {
		color: #8b93a7;
		font-size: 0.82rem;
	}
	code {
		background: #1a2236;
		padding: 0.1rem 0.3rem;
		border-radius: 3px;
		font-size: 0.8rem;
	}
</style>
