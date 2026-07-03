<script lang="ts">
	import { page } from '$app/state';

	const links = [
		{ href: '/', label: 'Overview' },
		{ href: '/run', label: 'Run Experiment' },
		{ href: '/experiments', label: 'My Experiments' },
		{ href: '/benchmarks', label: 'Benchmarks' },
		{ href: '/reference', label: 'Reference' },
		{ href: '/requests', label: 'Requests' }
	];

	const isActive = (href: string) =>
		href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href);
</script>

<nav>
	<a class="brand" href="/">auspex<span class="brk">[</span>ai<span class="brk">]</span></a>
	<span class="tag">researcher</span>
	<ul>
		{#each links as link (link.href)}
			<li>
				<a href={link.href} class:active={isActive(link.href)}>{link.label}</a>
			</li>
		{/each}
	</ul>
</nav>

<style>
	nav {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 0.75rem 1.25rem;
		border-bottom: 1px solid #1e2638;
		font-family: Inter, system-ui, sans-serif;
	}
	.brand {
		font-weight: 700;
		font-size: 1.15rem;
		color: #d4d4dc;
		text-decoration: none;
	}
	.brk {
		color: #a78bfa;
	}
	.tag {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b93a7;
		border: 1px solid #2a3450;
		border-radius: 3px;
		padding: 0.1rem 0.4rem;
	}
	ul {
		display: flex;
		gap: 0.5rem;
		list-style: none;
		margin: 0 0 0 auto;
		padding: 0;
	}
	a {
		color: #b8bfd0;
		text-decoration: none;
		padding: 0.35rem 0.6rem;
		border-radius: 4px;
		font-size: 0.9rem;
	}
	a.active {
		color: #fff;
		background: #1a2236;
	}
	a:hover {
		background: #161d2e;
	}
</style>
