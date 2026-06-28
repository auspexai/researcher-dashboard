<script lang="ts">
	// E15: `phase` is the optional coarse run_phase (queued/running/inert/
	// awaiting_assessment/…) — a muted suffix so the status pill stops conflating
	// the in-flight states. Omitted → unchanged behavior.
	let { status, phase }: { status: string | undefined; phase?: string | null } = $props();

	// Map lifecycle status → a tone class. Unknown statuses fall back to neutral.
	// Covers both experiment-lifecycle statuses and derived worker statuses
	// (active/offline/quarantined/retired) — the value sets don't collide.
	const tone: Record<string, string> = {
		submitted: 'neutral',
		approved: 'info',
		running: 'active',
		paused: 'warn',
		completed: 'ok',
		aborted: 'bad',
		archived: 'muted',
		// worker statuses
		active: 'active',
		offline: 'muted',
		quarantined: 'warn',
		retired: 'muted'
	};
	const cls = $derived(tone[status ?? ''] ?? 'neutral');
</script>

<span class="badge {cls}">{status ?? 'unknown'}</span>{#if phase}<span class="phase">· {phase.replace(/_/g, ' ')}</span>{/if}

<style>
	.badge {
		display: inline-block;
		font-size: 0.72rem;
		font-weight: 600;
		letter-spacing: 0.03em;
		padding: 0.12rem 0.5rem;
		border-radius: 999px;
		border: 1px solid transparent;
		text-transform: lowercase;
	}
	.neutral {
		color: #b8bfd0;
		background: #1a2236;
		border-color: #2a3450;
	}
	.info {
		color: #93c5fd;
		background: #10203a;
		border-color: #1e3a5f;
	}
	.active {
		color: #67e8f9;
		background: #0a2630;
		border-color: #155e6b;
	}
	.warn {
		color: #fbbf24;
		background: #251d09;
		border-color: #4a3a13;
	}
	.ok {
		color: #6ee7b7;
		background: #07251c;
		border-color: #135e44;
	}
	.bad {
		color: #fca5a5;
		background: #2a1115;
		border-color: #5e1f28;
	}
	.muted {
		color: #8b93a7;
		background: #141a28;
		border-color: #232c42;
	}
	.phase {
		color: #8b93a7;
		font-size: 0.72rem;
		margin-left: 0.35em;
		white-space: nowrap;
	}
</style>
