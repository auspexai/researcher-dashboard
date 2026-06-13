<script lang="ts">
	import { untrack } from 'svelte';
	import type { Experiment, ExperimentActivity } from '$lib/api';

	// The researcher/driver "heart monitor" (surface_liveness_and_activity_view_design.md).
	// Makes an experiment's LIVENESS legible at a glance: a pulse with rhythm
	// awareness (so a duty-cycle gap reads "between beats · next ~HH:MM", never a
	// flatline), connection vitals, a plain-language line, and the few numbers that
	// matter. The pulse is accumulated client-side from the polled activity
	// snapshot — no backend change (an SSE-fed pulse is the natural follow-up).
	let {
		experiment,
		activity,
		coordReachable = null,
		coordReconnecting = false
	}: {
		experiment: Experiment;
		activity: ExperimentActivity | null;
		coordReachable?: boolean | null;
		// Debounced intermediate: a probe just missed (e.g. a coordinator restart)
		// but we haven't hit the unreachable threshold — show "reconnecting…", not
		// a red alarm, so a routine deploy doesn't look like an outage.
		coordReconnecting?: boolean;
	} = $props();

	type Sample = { t: number; c: number };
	const MAX_SAMPLES = 160; // ~16 min at a 6s poll — enough to read a 5-min cadence
	let history = $state<Sample[]>([]);

	// A terminal experiment's heart is calm (done), not a worrying flatline.
	const live = $derived(
		experiment.status === 'approved' || experiment.status === 'running'
	);
	const terminal = $derived(
		experiment.status === 'completed' ||
			experiment.status === 'aborted' ||
			experiment.status === 'archived'
	);
	// Terminal outcome — success vs failure should read at a glance, not both gray.
	const completed = $derived(experiment.status === 'completed');
	const aborted = $derived(experiment.status === 'aborted');

	// Sample completions_total on every activity update (each poll reassigns the
	// prop, so this re-runs even across idle intervals — that's what draws the
	// baseline between beats). untrack keeps the history write from self-triggering.
	$effect(() => {
		const c = activity?.completions_total ?? 0;
		void experiment.status; // re-sample on status flips too
		const t = Date.now();
		untrack(() => {
			if (terminal) return; // freeze the trace once the run ends
			history = [...history, { t, c }].slice(-MAX_SAMPLES);
		});
	});

	// Per-interval beats: the delta in completed units between consecutive samples.
	type Beat = { t: number; delta: number };
	const beats = $derived<Beat[]>(
		history.slice(1).map((s, i) => ({ t: s.t, delta: Math.max(0, s.c - history[i].c) }))
	);
	const maxDelta = $derived(Math.max(1, ...beats.map((b) => b.delta)));
	const beatTimes = $derived(beats.filter((b) => b.delta > 0).map((b) => b.t));
	const lastBeatT = $derived(
		beatTimes.length
			? beatTimes[beatTimes.length - 1]
			: activity?.last_activity_at
				? Date.parse(activity.last_activity_at)
				: null
	);

	// Cadence: the median gap between beats. Only trustworthy with ≥3 beats; an
	// adaptive/event-driven run never earns a "next at" (graceful degradation).
	const cadenceMs = $derived.by(() => {
		if (beatTimes.length < 3) return null;
		const gaps = beatTimes.slice(1).map((t, i) => t - beatTimes[i]);
		const sorted = [...gaps].sort((a, b) => a - b);
		return sorted[Math.floor(sorted.length / 2)];
	});

	let now = $state(Date.now());
	$effect(() => {
		if (terminal) return;
		const id = setInterval(() => (now = Date.now()), 1000);
		return () => clearInterval(id);
	});

	const sinceLastBeatMs = $derived(lastBeatT != null ? now - lastBeatT : null);
	const nextBeatT = $derived(
		live && cadenceMs != null && lastBeatT != null ? lastBeatT + cadenceMs : null
	);

	function ago(ms: number | null): string {
		if (ms == null) return '—';
		const s = Math.max(0, Math.round(ms / 1000));
		if (s < 60) return `${s}s ago`;
		const m = Math.round(s / 60);
		return m < 60 ? `${m}m ago` : `${Math.round(m / 60)}h ago`;
	}
	function clock(t: number | null): string {
		if (t == null) return '—';
		return new Date(t).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	const completions = $derived(activity?.completions_total ?? 0);
	const target = $derived(activity?.replication_target_total ?? 0);
	const contributors = $derived(activity?.active_contributor_count ?? 0);

	// One plain-language line — state in words.
	const narration = $derived.by(() => {
		if (terminal)
			return `${experiment.status} · ${completions} units attested${
				target ? ` of ${target}` : ''
			}`;
		if (!live) return `${experiment.status} · awaiting the network`;
		// The contributor COUNT lives in the vitals (with its dot); the line
		// speaks to the rhythm, not the headcount.
		const parts: string[] = [];
		if (lastBeatT != null) parts.push(`last beat ${ago(sinceLastBeatMs)}`);
		if (nextBeatT != null) {
			const due = nextBeatT - now;
			parts.push(due > 0 ? `next ~${clock(nextBeatT)}` : 'next beat due');
		} else if (lastBeatT != null) {
			parts.push('cadence learning…');
		}
		return parts.length ? parts.join(' · ') : 'waiting for the first beat…';
	});

	// Are we "between beats" on a known cadence? (the reassurance the overnight run lacked)
	const betweenBeats = $derived(
		live && nextBeatT != null && nextBeatT - now > 0 && (sinceLastBeatMs ?? 0) > 4000
	);
	const pct = $derived(target > 0 ? Math.min(100, Math.round((completions / target) * 100)) : null);
</script>

<section class="heart" class:live class:terminal>
	<header>
		<div
			class="pulse-dot"
			class:beating={live && !betweenBeats}
			class:between={betweenBeats}
			class:done-ok={completed}
			class:done-bad={aborted}
		></div>
		<h3>Activity</h3>
		<span class="status">{experiment.status ?? 'unknown'}</span>
	</header>

	<!-- the pulse strip: one bar per sampled interval, height ∝ units that interval -->
	<div class="strip" role="img" aria-label="activity pulse">
		{#if beats.length === 0}
			<p class="empty">{terminal ? 'run complete' : 'listening for the first beat…'}</p>
		{:else}
			{#each beats as b (b.t)}
				<span
					class="bar"
					class:beat={b.delta > 0}
					style="height: {b.delta > 0 ? 18 + Math.round((b.delta / maxDelta) * 46) : 2}px"
					title="{b.delta} units · {clock(b.t)}"
				></span>
			{/each}
		{/if}
	</div>

	<p class="narration" class:reassure={betweenBeats} class:good={completed} class:bad={aborted}>
		{narration}
	</p>

	<div class="vitals">
		<span class="vital" class:bad={coordReachable === false && !coordReconnecting}>
			<i
				class="dot"
				class:ok={coordReachable === true && !coordReconnecting}
				class:down={coordReachable === false && !coordReconnecting}
				class:reconnecting={coordReconnecting}
			></i>
			coordinator {coordReconnecting
				? 'reconnecting…'
				: coordReachable === false
					? 'unreachable'
					: coordReachable === true
						? 'up'
						: 'checking…'}
		</span>
		<span class="vital">
			<i class="dot" class:ok={contributors > 0}></i>
			{contributors} contributing
		</span>
		{#if activity?.network_active_workers != null}
			<span class="vital muted">{activity.network_active_workers} on the network</span>
		{/if}
	</div>

	<div class="metrics">
		<div class="metric">
			<span class="n">{completions}{target ? `/${target}` : ''}</span>
			<span class="l">units attested</span>
		</div>
		{#if pct != null}
			<div class="metric grow">
				<div class="progress"><div class="fill" style="width: {pct}%"></div></div>
				<span class="l">{pct}% replicated</span>
			</div>
		{/if}
		<div class="metric">
			<span class="n">{activity?.total_work_units ?? 0}</span>
			<span class="l">work units</span>
		</div>
	</div>
</section>

<style>
	.heart {
		border: 1px solid #2a3450;
		border-radius: 12px;
		background: linear-gradient(180deg, #121a2e 0%, #0e1424 100%);
		padding: 1rem 1.1rem;
		display: flex;
		flex-direction: column;
		gap: 0.7rem;
	}
	.heart.live {
		border-color: #155e6b;
	}
	header {
		display: flex;
		align-items: center;
		gap: 0.55rem;
	}
	h3 {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 600;
		color: #dbe2f0;
	}
	.status {
		margin-left: auto;
		font-size: 0.72rem;
		color: #8b93a7;
		text-transform: lowercase;
	}
	.pulse-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: #2a3450;
	}
	.pulse-dot.done-ok {
		background: #6ee7b7;
	}
	.pulse-dot.done-bad {
		background: #fca5a5;
	}
	.pulse-dot.beating {
		background: #67e8f9;
		box-shadow: 0 0 0 0 rgba(103, 232, 249, 0.6);
		animation: beat 1.1s ease-out infinite;
	}
	.pulse-dot.between {
		background: #4a7dff;
	}
	@keyframes beat {
		0% {
			box-shadow: 0 0 0 0 rgba(103, 232, 249, 0.55);
		}
		70% {
			box-shadow: 0 0 0 8px rgba(103, 232, 249, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(103, 232, 249, 0);
		}
	}
	.strip {
		display: flex;
		align-items: flex-end;
		gap: 2px;
		height: 70px;
		padding: 4px 2px;
		background: #0a1120;
		border-radius: 8px;
		border: 1px solid #1a2236;
		overflow: hidden;
	}
	.bar {
		flex: 0 0 3px;
		min-width: 3px;
		background: #233049;
		border-radius: 2px;
		align-self: flex-end;
	}
	.bar.beat {
		background: #67e8f9;
	}
	.empty {
		margin: auto;
		color: #5b6478;
		font-size: 0.8rem;
	}
	.narration {
		margin: 0;
		font-size: 0.86rem;
		color: #b8bfd0;
	}
	.narration.reassure {
		color: #4a7dff;
	}
	.narration.good {
		color: #6ee7b7;
	}
	.narration.bad {
		color: #fca5a5;
	}
	.vitals {
		display: flex;
		flex-wrap: wrap;
		gap: 0.9rem;
		font-size: 0.76rem;
		color: #9aa3b8;
	}
	.vital {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.vital.bad {
		color: #fca5a5;
	}
	.vital.muted {
		color: #6b7488;
	}
	.dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: #2a3450;
	}
	.dot.ok {
		background: #6ee7b7;
	}
	.dot.down {
		background: #fca5a5;
	}
	.dot.reconnecting {
		background: #fbbf24;
		animation: pulse-amber 1.2s ease-out infinite;
	}
	@keyframes pulse-amber {
		0% {
			box-shadow: 0 0 0 0 rgba(251, 191, 36, 0.5);
		}
		70% {
			box-shadow: 0 0 0 5px rgba(251, 191, 36, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(251, 191, 36, 0);
		}
	}
	.metrics {
		display: flex;
		align-items: center;
		gap: 1.3rem;
	}
	.metric {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.metric.grow {
		flex: 1;
	}
	.metric .n {
		font-size: 1.05rem;
		font-weight: 600;
		color: #e6ebf5;
		font-variant-numeric: tabular-nums;
	}
	.metric .l {
		font-size: 0.68rem;
		color: #7c849a;
		text-transform: uppercase;
		letter-spacing: 0.04em;
	}
	.progress {
		height: 7px;
		background: #1a2236;
		border-radius: 999px;
		overflow: hidden;
	}
	.fill {
		height: 100%;
		background: linear-gradient(90deg, #155e6b, #67e8f9);
		transition: width 0.5s ease;
	}
</style>
