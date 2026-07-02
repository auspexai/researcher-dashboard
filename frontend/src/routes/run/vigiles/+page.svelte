<script lang="ts">
	// The Vigiles capability page — what it IS and how to run THIS specific
	// starter. Capability-specific only: the general, capability-agnostic
	// material (onboarding, SDK, ethics, how to analyze results) lives once under
	// /reference, which this page links to rather than re-hosting.
	const VIGILES_REPO = 'https://github.com/auspexai/vigiles-tenant';
</script>

<p class="back"><a href="/run">← Run Experiment</a></p>

<div class="head">
	<span class="badge">certified starter</span>
	<h1>Vigiles</h1>
</div>
<p class="lead">
	A curated, <strong>declawed</strong> drift-probe experiment — the no-code way to see the
	AuspexAI network end-to-end before you bring your own tenant.
</p>

<section>
	<h2>What it is</h2>
	<p>
		Vigiles repeatedly probes a local model for behavioural drift and runs that probe through the
		full pipeline: replicated execution across volunteer workers, consensus within a
		<em>declared, calibrated tolerance envelope</em> (a version-skewed worker is a recorded
		outlier, never hidden), and a signed, Rekor-anchored <em>evidence bundle</em> you take custody
		of. The starter also ships a complete <strong>pre-registered design</strong> — its hypothesis,
		analysis, and stopping rule are notarized in the public transparency log <em>before</em> any
		data exists, so your bundle proves <code>design ≺ data</code>. It is
		<strong>package-bound and certified</strong> (the certificate locks the tolerance envelope
		too), so it clears the submission gate for any <strong>R1+</strong> researcher with no code
		review — the safest possible first run.
	</p>
</section>

<section>
	<h2>Run it</h2>
	<ol>
		<li>
			<strong>Be onboarded.</strong> Run <code>auspexai-tenant apply</code> (GitHub sign-in) — it
			<strong>generates your tenant signing key</strong> at
			<code>~/.config/auspexai-tenant/tenant_key</code> and submits your application signed by it
			(that key is your tenant credential from here on). Wait for approval; the
			<a href="/">Overview</a> goes green when your tenant is bound.
		</li>
		<li>
			<strong>Get the starter.</strong> Clone
			<a href={VIGILES_REPO} target="_blank" rel="noopener noreferrer">vigiles-tenant</a>
			— it ships the <code>experiment.toml</code> + package, ready to run unchanged.
		</li>
		<li>
			<strong>Run it.</strong> From inside the cloned repo, one command does the whole
			lifecycle — build, submit, wait for the maintainer's approval, then drive:
			<pre><code>cd vigiles-tenant
auspexai-tenant experiment launch --profile starter</code></pre>
			It finds <code>experiment.toml</code> by walking up from the repo and reuses the same
			<code>tenant_key</code> that <code>apply</code> created; <code>--profile starter</code>
			selects the certified, pre-registered configuration.
			Driving begins automatically on approval. <strong>Ctrl-C aborts the run cleanly</strong>
			— server-side too, so nothing is left orphaned; pass <code>--resumable</code> to instead
			leave it running and pick it up later with
			<code>auspexai-tenant experiment run latest</code> (transient network blips are retried
			automatically). <span class="aside">Prefer the dashboard? Point it at the repo with
				<code>WORKSPACE_DIR</code> and the <a href="/run">Run your workspace</a> Build → Submit →
				Run controls do the same.</span>
		</li>
		<li>
			<strong>Take custody.</strong> When it converges, collect + verify the evidence bundle:
			<pre><code>auspexai-tenant experiment export latest --verify</code></pre>
			It lands organized under <code>runs/&lt;label&gt;/bundle.json</code>. The verify chain
			checks the whole story: custody + worker signatures, the attested result set,
			<code>tolerance: ok</code> (the consensus evidence recomputes), <code>pre-reg: ok</code>
			and <code>design&lt;data: ok</code> (the design provably preceded the data — the ordering
			anchor lands on the hourly transparency-log sweep, so it may read
			<em>pending</em> right after a run).
			<span class="aside">Now analyze it → <a href="/reference">Reference › Understand your
					results</a> — how to read it, what every column means, and the analysis recipes.</span>
		</li>
	</ol>
</section>

<section>
	<h2>Vigiles reference</h2>
	<ul class="links">
		<li>
			<a href={VIGILES_REPO} target="_blank" rel="noopener noreferrer">vigiles-tenant ↗</a>
			— the certified starter's source: its <code>experiment.toml</code> (incl. the declared
			feature schema), the drift driver, and the package. Copy it as the template for your own
			tenant.
		</li>
	</ul>
	<p class="general">
		General docs — onboarding, the SDK, research ethics, and how to analyze your results — live in
		<a href="/reference">Reference</a>, not here, so they're the same for every experiment.
	</p>
</section>

<style>
	.back {
		margin: 0 0 0.5rem;
	}
	.back a {
		color: #7aa2ff;
		text-decoration: none;
		font-size: 0.85rem;
	}
	.back a:hover {
		text-decoration: underline;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 0.6rem;
	}
	.head h1 {
		margin: 0;
		font-weight: 700;
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
	.lead {
		color: #b8bfd0;
		max-width: 64ch;
	}
	.aside {
		display: block;
		margin-top: 0.5rem;
		color: #8b93a7;
		font-size: 0.82rem;
	}
	.general {
		margin-top: 0.75rem;
		color: #8b93a7;
		font-size: 0.84rem;
	}
	section {
		margin-top: 1.5rem;
	}
	h2 {
		font-size: 0.95rem;
		color: #e6e9f0;
		margin: 0 0 0.5rem;
	}
	p,
	li {
		color: #cdd5e6;
		font-size: 0.9rem;
		line-height: 1.55;
	}
	ol {
		padding-left: 1.2rem;
	}
	ol li {
		margin: 0.5rem 0;
	}
	.links {
		list-style: none;
		padding: 0;
	}
	.links li {
		margin: 0.5rem 0;
	}
	.links a {
		color: #7aa2ff;
		text-decoration: none;
		font-weight: 600;
	}
	.links a:hover {
		text-decoration: underline;
	}
	a:not(.links a):not(.back a) {
		color: #7aa2ff;
		text-decoration: none;
	}
	a:not(.links a):not(.back a):hover {
		text-decoration: underline;
	}
	pre {
		margin: 0.5rem 0;
		background: #0a1020;
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.6rem 0.8rem;
		overflow-x: auto;
	}
	code {
		font-family: ui-monospace, monospace;
		background: #1a2236;
		padding: 0.05rem 0.3rem;
		border-radius: 3px;
		color: #cdd5e6;
		font-size: 0.85rem;
	}
	pre code {
		background: none;
		padding: 0;
		color: #b8e8d8;
	}
</style>
