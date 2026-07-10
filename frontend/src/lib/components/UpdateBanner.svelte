<script lang="ts">
	// Update-available notice (mirrors the worker dashboard's): if a newer R-D or
	// tenant-sdk has been announced on the coordinator, surface it so the
	// researcher can elect to upgrade. Best-effort + dismissible; silent when
	// current or the coordinator is unreachable.
	import { onMount } from 'svelte';
	import { api, type UpdatesResponse } from '$lib/api';

	let info = $state<UpdatesResponse | null>(null);
	let dismissed = $state(false);

	onMount(async () => {
		try {
			info = await api.updates();
		} catch {
			info = null;
		}
	});

	const items = $derived(
		[
			{ name: 'Researcher Dashboard', c: info?.dashboard },
			{ name: 'tenant-sdk', c: info?.sdk }
		].filter((x) => x.c?.update_available)
	);
</script>

{#if items.length && !dismissed}
	<div class="update-banner" role="status">
		<span class="tag">Update available</span>
		<span class="msg">
			{#each items as it (it.name)}
				<span class="pill"
					><strong>{it.name} v{it.c?.latest}</strong>
					<span class="cur">· you have v{it.c?.current ?? '—'}</span></span
				>
			{/each}
		</span>
		<button class="dismiss" onclick={() => (dismissed = true)} aria-label="Dismiss update notice"
			>×</button
		>
	</div>
{/if}

<style>
	.update-banner {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		max-width: 960px;
		margin: 0.75rem auto 0;
		padding: 0.5rem 0.9rem;
		border-radius: 8px;
		background: #1c1740;
		border: 1px solid #3b2f7a;
		color: #cdc6f0;
		font-size: 0.85rem;
	}
	.tag {
		font-weight: 700;
		color: #b9a7ff;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		font-size: 0.72rem;
		white-space: nowrap;
	}
	.msg {
		display: flex;
		gap: 0.75rem;
		flex-wrap: wrap;
	}
	.cur {
		color: #8b84b0;
	}
	.dismiss {
		margin-left: auto;
		background: none;
		border: none;
		color: #8b84b0;
		font-size: 1.15rem;
		cursor: pointer;
		line-height: 1;
		padding: 0 0.2rem;
	}
	.dismiss:hover {
		color: #cdc6f0;
	}
</style>
