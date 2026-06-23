<script lang="ts">
	// The Vigiles starter hub — what it is, how to run it, and the reference
	// links (SDK docs, onboarding, ethics, best practices). The Swagger/ReDoc
	// analog from the ops console: a per-tenant detail/docs page; for the
	// certified starter it doubles as the learning front door.
	const ONBOARDING = 'https://github.com/auspexai/.github/blob/main/ONBOARDING.md';
	const SDK_README = 'https://github.com/auspexai/tenant-sdk#readme';
	const VIGILES_REPO = 'https://github.com/auspexai/vigiles-tenant';
	const ETHICS = 'https://github.com/auspexai/.github/blob/main/RESEARCH_ETHICS_POLICY.md';
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
		full pipeline: replicated execution across volunteer workers, hash-agreement consensus, and a
		signed, Rekor-anchored <em>evidence bundle</em> you take custody of. It is
		<strong>package-bound and certified</strong>, so it clears the submission gate for any
		<strong>R1+</strong> researcher with no code review — the safest possible first run.
	</p>
</section>

<section>
	<h2>Run it</h2>
	<ol>
		<li>
			<strong>Be onboarded.</strong> Apply with <code>auspexai-tenant apply</code> (GitHub
			sign-in) and wait for approval — the
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
auspexai-tenant experiment launch</code></pre>
			No flags needed — it finds <code>experiment.toml</code> and your tenant key on its own.
			Driving begins automatically on approval (Ctrl-C is safe — re-run to resume from the
			journal). <span class="aside">Prefer the dashboard? Point it at the repo with
				<code>WORKSPACE_DIR</code> and the <a href="/run">Run your workspace</a> Build → Submit →
				Run controls do the same.</span>
		</li>
		<li>
			<strong>Take custody.</strong> When it converges, collect + verify the evidence bundle:
			<pre><code>auspexai-tenant experiment export latest --verify</code></pre>
			It lands organized under <code>runs/&lt;label&gt;/bundle.json</code>.
		</li>
	</ol>
</section>

<section>
	<h2>Reference &amp; best practices</h2>
	<ul class="links">
		<li>
			<a href={ONBOARDING} target="_blank" rel="noopener noreferrer">Onboarding guide ↗</a>
			— from install to a bound tenant in four steps.
		</li>
		<li>
			<a href={SDK_README} target="_blank" rel="noopener noreferrer">Tenant SDK — capability map ↗</a>
			— author, submit, drive, and the evidence verify chain.
		</li>
		<li>
			<a href={VIGILES_REPO} target="_blank" rel="noopener noreferrer">vigiles-tenant ↗</a>
			— the starter's source; copy it as the template for your own tenant.
		</li>
		<li>
			<a href={ETHICS} target="_blank" rel="noopener noreferrer">Research ethics policy ↗</a>
			— risk classes, review, and what bringing your own code (R2+) entails.
		</li>
	</ul>
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
