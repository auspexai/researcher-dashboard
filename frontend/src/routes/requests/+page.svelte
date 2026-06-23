<script lang="ts">
	// The in-app demand-board was retired (design D2): requests now live on the
	// AuspexAI community forum — GitHub Discussions — a public, votable place
	// maintainers triage alongside the code, instead of a second queue in the
	// dashboard. This page is the launchpad.
	const DISCUSSIONS = 'https://github.com/auspexai/.github/discussions';
	const NEW = 'https://github.com/auspexai/.github/discussions/new/choose';
</script>

<h1>Requests</h1>
<p class="lead">
	Need a model the network doesn't serve, or a capability that doesn't exist yet? Requests live on
	the AuspexAI community forum — a public, up-votable place the maintainers triage alongside the
	code.
</p>

<div class="card">
	<p class="kinds-intro">Two kinds of request:</p>
	<ul class="kinds">
		<li>
			<strong>Model requests</strong> — a model (and quantization) the network should serve.
		</li>
		<li>
			<strong>Capability requests</strong> — a new worker capability or platform feature your
			research needs.
		</li>
	</ul>
	<div class="actions">
		<a class="cta" href={NEW} target="_blank" rel="noopener noreferrer">Open a request ↗</a>
		<a class="ghost" href={DISCUSSIONS} target="_blank" rel="noopener noreferrer"
			>Browse all requests ↗</a
		>
	</div>
</div>

<p class="muted note">
	Posting in the open lets other researchers up-vote and add detail, so the maintainers can see real
	demand. Your GitHub identity is your handle there.
</p>

<style>
	h1 {
		font-weight: 700;
	}
	.lead {
		color: #b8bfd0;
		max-width: 64ch;
	}
	.card {
		border: 1px solid #1e2638;
		border-radius: 8px;
		background: #10182a;
		padding: 1.1rem 1.25rem;
		margin: 1rem 0;
		max-width: 64ch;
	}
	.kinds-intro {
		color: #e6e9f0;
		margin: 0 0 0.4rem;
		font-weight: 600;
		font-size: 0.9rem;
	}
	.kinds {
		margin: 0 0 1rem;
		padding-left: 1.1rem;
		color: #cdd5e6;
		font-size: 0.9rem;
	}
	.kinds li {
		margin: 0.3rem 0;
	}
	.actions {
		display: flex;
		gap: 0.75rem;
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
	a.ghost {
		color: #7aa2ff;
		border: 1px solid #2a3450;
		border-radius: 6px;
		padding: 0.45rem 1rem;
		text-decoration: none;
		font-size: 0.9rem;
	}
	a.ghost:hover {
		border-color: #3a4668;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
		max-width: 64ch;
	}
	.note {
		margin-top: 1rem;
	}
</style>
