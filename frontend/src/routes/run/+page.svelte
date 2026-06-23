<script lang="ts">
	import ExperimentSetup from '$lib/components/ExperimentSetup.svelte';

	// The launcher home: start a run (the Vigiles starter or your own workspace)
	// here. Monitoring + the run list live on My Experiments — this page stays a
	// pure launcher, no duplicate list.
</script>

<h1>Run Experiment</h1>
<p class="lead">Start a run — the certified Vigiles starter, or your own workspace.</p>

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
