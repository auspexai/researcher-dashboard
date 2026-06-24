<script lang="ts">
	import { onMount } from 'svelte';
	import ExperimentSetup from '$lib/components/ExperimentSetup.svelte';
	import { api, type Experiment } from '$lib/api';

	// The launcher home: start a run (the Vigiles starter or your own workspace)
	// here. Monitoring + the run list live on My Experiments — this page stays a
	// pure launcher, no duplicate list.

	// …but a run kicked off from the CLI (or here) won't tell you WHERE it went.
	// So we poll the coordinator (the shared state the CLI also writes to) and
	// surface a deep-link nudge to any LIVE run — the dashboard NOTICES the run
	// and points you at its detail page. No CLI→browser push needed.
	const TERMINAL = new Set(['completed', 'aborted', 'archived']);
	let liveRuns = $state<Experiment[]>([]);

	async function refreshLive() {
		try {
			const data = await api.listExperiments();
			liveRuns = (data.experiments ?? [])
				.filter((e) => !TERMINAL.has(e.status ?? ''))
				.sort((a, b) => (b.submitted_at ?? '').localeCompare(a.submitted_at ?? ''));
		} catch {
			/* best-effort nudge — never blocks the launcher */
		}
	}

	onMount(() => {
		refreshLive();
		const timer = setInterval(refreshLive, 5000);
		return () => clearInterval(timer);
	});
</script>

<h1>Run Experiment</h1>
<p class="lead">Start a run — the certified Vigiles starter, or your own workspace.</p>

<!-- Live-run nudge: the gap a CLI launch leaves ("where did it go?"). Polls the
     coordinator; when a run is live it deep-links you straight to its detail. -->
{#if liveRuns.length > 0}
	{@const top = liveRuns[0]}
	<a class="live-nudge" href="/experiments/{top.experiment_id}">
		<span class="live-dot"></span>
		<span class="live-text"
			>Your run <strong>{top.tenant_experiment_label ?? top.experiment_id}</strong> is live
			<span class="live-status">{top.status}</span> — watch it →</span
		>
		{#if liveRuns.length > 1}<span class="live-more">+{liveRuns.length - 1} more</span>{/if}
	</a>
{/if}

<!-- Pinned: the declawed certified starter. Always available, for a first run
     and forever after. Its sub-page is the what-is-Vigiles + how-to hub. -->
<div class="starter">
	<div class="starter-head">
		<span class="badge">certified starter</span>
		<h2>Vigiles</h2>
	</div>
	<p class="starter-desc">
		A curated, declawed drift-probe experiment that runs out of the box — no code to write.
		It exercises the whole loop (submit → replicated execution → consensus → a verified,
		Rekor-anchored evidence bundle) so you can see the network work end-to-end before bringing
		your own tenant.
	</p>
	<div class="starter-actions">
		<a class="cta" href="/run/vigiles">Learn &amp; run Vigiles →</a>
		<span class="hint">low-risk · package-bound · any R1+ researcher</span>
	</div>
</div>

<!-- The run controls: build → submit → run the configured workspace (the Vigiles
     starter or your own). Gates itself on the workspace / local-exec state. -->
<h2 class="section">Run your workspace</h2>
<ExperimentSetup />

<p class="muted see-all">
	Your runs appear on <a href="/experiments">My Experiments</a> once the coordinator accepts them.
</p>

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
	}
	.live-nudge {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		margin: 0.9rem 0 0.3rem;
		padding: 0.6rem 0.9rem;
		border: 1px solid #1d7f90;
		border-left-width: 4px;
		border-radius: 8px;
		background: linear-gradient(180deg, rgba(21, 94, 107, 0.22), #10182a);
		color: #e0fbff;
		text-decoration: none;
		font-size: 0.9rem;
	}
	.live-nudge:hover {
		background: linear-gradient(180deg, rgba(26, 111, 126, 0.3), #122036);
	}
	.live-dot {
		flex: none;
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: #67e8f9;
		animation: nudge-beat 1.2s ease-out infinite;
	}
	@keyframes nudge-beat {
		0% {
			box-shadow: 0 0 0 0 rgba(103, 232, 249, 0.55);
		}
		70% {
			box-shadow: 0 0 0 7px rgba(103, 232, 249, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(103, 232, 249, 0);
		}
	}
	.live-status {
		color: #8bd9e8;
		text-transform: lowercase;
	}
	.live-more {
		margin-left: auto;
		font-size: 0.78rem;
		color: #8bd9e8;
	}
	.section {
		font-size: 0.95rem;
		margin: 1.5rem 0 0.5rem;
		color: #e6e9f0;
	}
	.starter {
		border: 1px solid #1d7f90;
		border-left-width: 4px;
		border-radius: 8px;
		background: linear-gradient(180deg, rgba(21, 94, 107, 0.18), #10182a);
		padding: 1.1rem 1.25rem;
		margin: 1rem 0 0.5rem;
	}
	.starter-head {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.starter-head h2 {
		margin: 0;
		font-size: 1.25rem;
		color: #e0fbff;
	}
	.badge {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #67e8f9;
		border: 1px solid #1d7f90;
		border-radius: 999px;
		padding: 0.1rem 0.5rem;
	}
	.starter-desc {
		color: #cdd5e6;
		font-size: 0.9rem;
		margin: 0.6rem 0 0.9rem;
		max-width: 60ch;
	}
	.starter-actions {
		display: flex;
		align-items: center;
		gap: 1rem;
		flex-wrap: wrap;
	}
	a.cta {
		background: #155e6b;
		color: #e0fbff;
		border: 1px solid #1d7f90;
		border-radius: 6px;
		padding: 0.45rem 1rem;
		text-decoration: none;
		font-weight: 600;
		font-size: 0.9rem;
	}
	a.cta:hover {
		background: #1a6f7e;
	}
	.hint {
		color: #8b93a7;
		font-size: 0.8rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.see-all {
		margin-top: 1.25rem;
	}
	.see-all a {
		color: #7aa2ff;
		text-decoration: none;
	}
	.see-all a:hover {
		text-decoration: underline;
	}
</style>
