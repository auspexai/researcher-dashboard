<script lang="ts">
	import Nav from '$lib/components/Nav.svelte';
	import UpdateBanner from '$lib/components/UpdateBanner.svelte';
	let { children } = $props();
</script>

<Nav />
<UpdateBanner />
<main>
	{@render children()}
</main>

<style>
	:global(body) {
		margin: 0;
		font-family: Inter, system-ui, sans-serif;
	}
	main {
		max-width: 960px;
		margin: 0 auto;
		padding: 1.5rem 1.25rem;
	}
</style>
