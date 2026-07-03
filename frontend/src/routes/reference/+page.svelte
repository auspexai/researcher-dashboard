<script lang="ts">
	// Reference — the researcher's general knowledge home, organized by the
	// research lifecycle (get started → run → understand results → trust & cite).
	// This is capability-AGNOSTIC: the standards every tenant builds on. Vigiles
	// (and future capabilities) are the worked exemplars under /run/<capability>;
	// they LINK here for the cross-cutting material rather than re-hosting it.
	const ONBOARDING = 'https://github.com/auspexai/.github/blob/main/ONBOARDING.md';
	const SDK_README = 'https://github.com/auspexai/tenant-sdk#readme';
	const ETHICS = 'https://github.com/auspexai/.github/blob/main/RESEARCH_ETHICS_POLICY.md';
	const READING_EVIDENCE =
		'https://github.com/auspexai/tenant-sdk/blob/main/docs/reading_your_evidence.md';
	const ANALYZING_RESULTS =
		'https://github.com/auspexai/tenant-sdk/blob/main/docs/analyzing_your_results.md';
</script>

<h1>Reference</h1>
<p class="lead">
	Everything a researcher needs, in the order you'll need it — independent of which experiment you
	run. (Capability-specific docs live on each capability's page, e.g.
	<a href="/run/vigiles">Vigiles</a>.)
</p>

<section>
	<h2>1 · Get started</h2>
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
			<a href={ETHICS} target="_blank" rel="noopener noreferrer">Research ethics policy ↗</a>
			— risk classes, review, and what bringing your own code (R2+) entails.
		</li>
	</ul>
</section>

<section>
	<h2>2 · Run &amp; profiles</h2>
	<p>
		Start from <a href="/run">Run Experiment</a> — the certified <a href="/run/vigiles">Vigiles</a>
		starter (no code) or your own workspace. The whole lifecycle is one command:
	</p>
	<pre><code>auspexai-tenant experiment launch     # build → submit → await approval → drive</code></pre>
	<p class="sub">
		Profiles (<code>--profile starter</code> / <code>research</code>) select named config
		override-sets — the starter is certified <em>and pre-registered</em> (its design is anchored
		before data exists); runs appear on <a href="/experiments">My Experiments</a> once the
		coordinator accepts them. If your analysis genuinely changes after you've seen data, declare
		it honestly: <code>auspexai-tenant experiment deviate latest --what "…" --why "…"</code> —
		an append-only, signed record; exploratory analysis is welcome, it just can't masquerade as
		confirmatory.
	</p>
</section>

<section class="highlight">
	<h2>3 · Understand your results</h2>
	<p>
		You have a verified evidence bundle — now read it. These two guides are the difference between
		a number you can defend and one you're guessing at. <strong>Read both:</strong> the first tells
		you <em>how much to trust</em> a row; the second tells you <em>what it means</em>.
	</p>
	<ul class="links">
		<li>
			<a href={READING_EVIDENCE} target="_blank" rel="noopener noreferrer"
				>Reading your evidence ↗</a
			>
			<span class="kind">trust</span>
			— verify first; stratify by corroboration (<code>integrity_basis</code>); weight by
			replication + independence; treat divergence as signal; cite the Rekor anchor.
		</li>
		<li>
			<a href={ANALYZING_RESULTS} target="_blank" rel="noopener noreferrer"
				>Analyzing your results ↗</a
			>
			<span class="kind">interpret</span>
			— the data dictionary, the <code>role</code> discipline (anchor vs summary), the
			<code>.valid</code> flag, and the analysis recipes. Vigiles is the worked example.
		</li>
	</ul>
	<p class="sub">
		Quickest start: <code>auspexai-tenant bundle table &lt;bundle&gt; --data-dictionary</code> prints,
		from the signed manifest, what every <code>output.*</code> column means (no pandas needed). For a
		frame: <code>load_verified(bundle)</code> or <code>bundle table -o results.csv</code>.
	</p>
	<p>
		<strong>Drift Benchmark.</strong> Declare a baseline once in your config
		(<code>[benchmark] reference = "&lt;experiment&gt;"</code>) and every launch scores the
		finished run against it automatically, in envelope units (1.0&nbsp;EU = the calibrated
		noise floor; headline = peak + breadth). The score appears on the run's
		<em>Benchmark</em> tab, the baseline's page shows its full track over time, and the
		<em>Drift</em> column on <a href="/experiments">My Experiments</a> gives the sweep.
		<code>auspexai-tenant benchmark publish &lt;run&gt;</code> submits a signed,
		self-grounding entry to the public board — admitted by verification, not by an editor.
		One-off comparisons: <code>auspexai-tenant benchmark drift</code>.
	</p>
</section>

<section>
	<h2>4 · Trust &amp; citation</h2>
	<p>
		Every result is wrapped in integrity context — replicated execution, consensus within a
		declared tolerance envelope (byte-exact where pinned), a signed Rekor-anchored attestation, a
		pre-registered design whose anchor provably precedes the data (<code>design ≺ data</code>),
		and an apparatus footprint — so a finding is externally defensible. The <a href={READING_EVIDENCE} target="_blank" rel="noopener noreferrer"
			>evidence guide ↗</a
		>
		covers verification + how to cite the transparency-log anchor; your experiment's
		<a href="/experiments">detail page</a> offers "Cite this work" once its attestation is anchored.
	</p>
</section>

<style>
	.lead {
		color: #b8bfd0;
		max-width: 66ch;
	}
	section {
		margin-top: 1.5rem;
	}
	section.highlight {
		border: 1px solid #2a3450;
		border-radius: 8px;
		padding: 0.9rem 1.1rem;
		background: #0e1424;
	}
	h1 {
		font-weight: 700;
		margin: 0 0 0.3rem;
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
	.sub {
		color: #8b93a7;
		font-size: 0.84rem;
	}
	.links {
		list-style: none;
		padding: 0;
	}
	.links li {
		margin: 0.6rem 0;
	}
	.links a {
		color: #7aa2ff;
		text-decoration: none;
		font-weight: 600;
	}
	.links a:hover {
		text-decoration: underline;
	}
	.kind {
		font-size: 0.66rem;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: #67e8f9;
		border: 1px solid #1d7f90;
		border-radius: 999px;
		padding: 0.05rem 0.4rem;
		margin-left: 0.3rem;
	}
	a:not(.links a) {
		color: #7aa2ff;
		text-decoration: none;
	}
	a:not(.links a):hover {
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
