<script lang="ts">
	import { page } from '$app/state';
	import {
		api,
		ApiError,
		type Attestation,
		type BundleVerification,
		type Citation,
		type Experiment,
		type ExperimentActivity,
		type Receipt,
		type ResultItem,
		type WorkUnits
	} from '$lib/api';
	import ErrorState from '$lib/components/ErrorState.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import ActivityHeart from '$lib/components/ActivityHeart.svelte';
	import LifecycleTimeline from '$lib/components/LifecycleTimeline.svelte';

	const id = $derived(page.params.id);
	let coordReachable = $state<boolean | null>(null);
	let coordReconnecting = $state(false);
	let coordFails = 0;
	const COORD_FAIL_THRESHOLD = 2; // consecutive misses before "unreachable" (smooths a deploy)

	let experiment = $state<Experiment | null>(null);
	let workUnits = $state<WorkUnits | null>(null);
	let activity = $state<ExperimentActivity | null>(null);
	let receipts = $state<Receipt[] | null>(null);
	let error = $state<ApiError | null>(null);
	let loading = $state(true);

	// Lifecycle actions (R-D4): `acting` is the in-flight action name (disables
	// the row); `confirming` is the destructive action awaiting confirmation;
	// `actionError` surfaces a refused action (e.g. a `conflict` reason).
	let acting = $state<string | null>(null);
	let confirming = $state<string | null>(null);
	let actionError = $state<ApiError | null>(null);

	// Integrity panel (R-D inc-1). The final attestation auto-loads for a
	// completed experiment; mid-run, a checkpoint attestation is fetched only on
	// explicit request (it's rebuilt on demand coordinator-side).
	let attestation = $state<Attestation | null>(null);
	let attestationError = $state<ApiError | null>(null);
	let attestationLoading = $state(false);

	// Cite this work (System B, D): the contributor/acknowledgment block for a
	// completed experiment — PI + opted-in volunteers + anonymous count. It's the
	// publish-prep surface, separate from collection: the researcher returns to it
	// when their analysis is done and they're ready to put the result in the world.
	let citation = $state<Citation | null>(null);
	let citationLoading = $state(false);
	let citeCopied = $state(false);

	// Results delivery (R-D5). Loaded separately from the experiment so the
	// consensus/raw toggle + pagination don't refetch the whole page.
	let results = $state<ResultItem[] | null>(null);
	let resultsCursor = $state<string | null>(null);
	let resultsInclude = $state<'consensus' | 'raw'>('consensus');
	let resultsLoading = $state(false);
	let resultsError = $state<ApiError | null>(null);
	let exporting = $state(false);
	let exportMsg = $state<string | null>(null);

	// Detail-page tabs (declutter): Progress (the live run), Evidence (integrity,
	// receipts, citation), Export (results + bundle collect/verify). The live
	// header — status, timeline, heart — stays above the tabs.
	let tab = $state<'progress' | 'evidence' | 'export'>('progress');
	// Local verify-on-collect: the dashboard backend runs the SDK's verify_bundle
	// on the collected bundle (on this machine) and returns the named-check result.
	let verification = $state<BundleVerification | null>(null);

	const fmt = (iso: string | undefined) => (iso ? new Date(iso).toLocaleString() : '—');

	// Plain-language glosses for the footprint's worker/platform codes, surfaced at
	// the point of use so a researcher needn't keep a glossary (D10b / evidence
	// literacy). The corroboration-basis codes get an inline meaning too — they're
	// the load-bearing ones for "stratify, don't pool".
	const BASIS_GLOSS: Record<string, string> = {
		process_only: 'one worker ran it — no cross-check',
		within_cell_exact: 'independent workers produced the identical result',
		within_cell_tolerance: 'independent workers agreed within tolerance',
		diverged: 'workers disagreed — recorded, never hidden'
	};
	const basisLabel = (b: string) => b.replace(/_/g, ' ');

	// D10b: value-level glosses for the footprint's remaining coded fields, at the
	// point of use (the corroboration-basis codes have BASIS_GLOSS above). Every
	// footprint field is a firewall-#2 apparatus condition meant for the
	// researcher — none are worker-internal, so none are hidden; these just make
	// the codes legible. `humanize` turns a snake_case taxonomy code (e.g. the
	// research_class "refusal_boundary_mapping") into readable text.
	const CONTAINMENT_GLOSS: Record<string, string> = {
		permissive: 'permissive: ordinary OS process isolation (no kernel sandbox)',
		strict: 'strict: hardened kernel sandbox — seccomp syscall filter + namespaces + cgroup caps'
	};
	const APPROVAL_GLOSS: Record<string, string> = {
		auto: 'auto-approved — the tenant tier/standing cleared the envelope checks',
		human: 'human-reviewed — a maintainer approved this experiment'
	};
	const glossOf = (m: Record<string, string>, k: string | undefined | null) =>
		k ? (m[k] ?? '') : '';
	const humanize = (s: string | undefined | null) => (s ? s.replace(/_/g, ' ') : '—');

	// C7 Inc 4: plain-language "how this unit agreed" for a tolerance consensus
	// row — the point-of-use legibility the bare hash never gave (a tolerance run
	// reads "corroborated within the envelope, spread Δ, M outliers"). The tooltip
	// details each feature's observed spread against its declared allowance.
	type TolEvidence = NonNullable<ResultItem['consensus_evidence']>;
	function tolSummary(ev: TolEvidence): string {
		const n = ev.agreeing_workers ?? 0;
		// C17 observe-only: no agreement is claimed — each replica is an
		// independent observation, by design (never a fault to interpret).
		if (ev.method === 'builtin_process_only') {
			return `${n} independent observation${n === 1 ? '' : 's'} · observe-only (no agreement claimed — by design)`;
		}
		const o = ev.outlier_count ?? 0;
		const agreed = `${n} worker${n === 1 ? '' : 's'} agreed within tolerance`;
		return o > 0 ? `${agreed} · ${o} outlier${o === 1 ? '' : 's'} recorded` : agreed;
	}
	function tolDetail(ev: TolEvidence): string {
		if (ev.method === 'builtin_process_only') {
			return (
				'Observe-only collection: every replica is an independent, valid observation — ' +
				'no cross-worker agreement is claimed, so differing outputs are the design, not ' +
				'a fault. The attestation binds a deterministic representative hash (not a ' +
				'consensus value); every observation is anchored in the signed receipts.'
			);
		}
		const lines: string[] = [
			'Replicas agreed within the declared tolerance envelope; the consensus value is the ' +
				'deterministic representative (its hash is what the attestation binds). ' +
				'Observed spread vs allowed, per feature:'
		];
		const env = ev.envelope ?? {};
		for (const [feat, sp] of Object.entries(ev.spread ?? {})) {
			const e = env[feat] ?? {};
			let allowed: string;
			if (e.rule === 'set_jaccard') allowed = `set overlap ≥ ${e.min}`;
			else if (e.rule === 'categorical_exact') allowed = 'must match exactly';
			else
				allowed =
					[e.rel != null ? `rel ≤ ${e.rel}` : '', e.abs != null ? `abs ≤ ${e.abs}` : '']
						.filter(Boolean)
						.join(', ') || 'declared rule';
			const observed = e.rule === 'set_jaccard' ? `set distance ${sp}` : `spread ${sp}`;
			lines.push(`${feat}: ${observed} (allowed: ${allowed})`);
		}
		return lines.join('\n');
	}

	// Fetch a page of results (consensus or raw). `reset` replaces the list and
	// clears the cursor; otherwise it appends the next page (Load more).
	async function loadResults(
		current: string,
		include: 'consensus' | 'raw',
		opts: { reset?: boolean } = {}
	) {
		if (opts.reset) {
			results = null;
			resultsCursor = null;
			resultsError = null;
		}
		resultsLoading = true;
		try {
			const page = await api.getResults(current, {
				include,
				cursor: opts.reset ? undefined : (resultsCursor ?? undefined)
			});
			const items = page.results ?? [];
			results = opts.reset ? items : [...(results ?? []), ...items];
			resultsCursor = page.next_cursor ?? null;
		} catch (e) {
			if (opts.reset) resultsError = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			resultsLoading = false;
		}
	}

	// Fetch the result-set attestation. Final for a completed experiment;
	// `checkpoint` asks for a partial consensus-so-far attestation mid-run.
	async function loadAttestation(current: string, opts: { checkpoint?: boolean } = {}) {
		attestationLoading = true;
		attestationError = null;
		try {
			attestation = await api.getAttestation(current, opts);
		} catch (e) {
			attestation = null;
			attestationError = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			attestationLoading = false;
		}
	}

	// Best-effort: the citation block for a completed experiment. On failure the
	// section simply doesn't render — it's never load-bearing for the page.
	async function loadCitation(current: string) {
		citationLoading = true;
		try {
			citation = await api.getCitation(current);
		} catch {
			citation = null;
		} finally {
			citationLoading = false;
		}
	}

	// Collect the offload bundle: save it (the shared runs/<label>/ layout, same
	// as the CLI) + report the custody transfer. Falls back to a browser
	// download only if the dashboard couldn't write to disk.
	async function doExport() {
		const current = id;
		if (!current || exporting) return;
		exporting = true;
		exportMsg = null;
		verification = null;
		try {
			const { bundle, verification: v, saved_path } = await api.exportResults(
				current,
				experiment?.tenant_experiment_label
			);
			verification = v;
			const t = bundle.transfer;
			const unified = t?.root_kind?.startsWith('result-set');
			const custody = t
				? `Collected — data custody transferred to you (transfer ${t.transfer_id}${
						unified ? '; custody signs the attested merkle root' : ''
					}).`
				: 'Collected.';
			if (saved_path) {
				exportMsg = `${custody} Saved to ${saved_path}.`;
			} else {
				// Disk write unavailable (e.g. permissions) → browser download fallback.
				const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
				const url = URL.createObjectURL(blob);
				const a = document.createElement('a');
				a.href = url;
				a.download = `${current}-bundle.json`;
				a.click();
				URL.revokeObjectURL(url);
				exportMsg = `${custody} Couldn't write to runs/ — downloaded ${current}-bundle.json instead.`;
			}
			await load(current, { silent: true }); // refresh results_collected_at
		} catch (e) {
			exportMsg = `Export failed: ${e instanceof ApiError ? e.message : String(e)}`;
		} finally {
			exporting = false;
		}
	}

	// Load the experiment + its (independently non-fatal) secondary views. On the
	// initial/route-change load we show the full loading state; a post-action
	// refetch is `silent` so the page doesn't flash back to "Loading…".
	async function load(current: string, opts: { silent?: boolean } = {}) {
		if (!opts.silent) {
			loading = true;
			error = null;
			experiment = null;
			workUnits = null;
			activity = null;
			receipts = null;
		}
		try {
			experiment = await api.getExperiment(current);
			try {
				workUnits = await api.getWorkUnits(current);
			} catch {
				/* secondary — keep prior value */
			}
			try {
				activity = await api.getExperimentActivity(current);
			} catch {
				/* secondary — keep prior value */
			}
			try {
				receipts = (await api.getExperimentReceipts(current)).receipts ?? [];
			} catch {
				/* secondary — keep prior value */
			}
			// The final attestation exists only once COMPLETED (it is persisted
			// + canonical there). Mid-run the panel offers a checkpoint instead.
			if (experiment?.status === 'completed') {
				await loadAttestation(current);
				loadCitation(current); // publish-prep block; non-blocking
			} else if (!opts.silent) {
				attestation = null;
				attestationError = null;
			}
		} catch (e) {
			if (!opts.silent) error = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			if (!opts.silent) loading = false;
		}
	}

	// Run a lifecycle action, then silently refetch so the status badge + fields
	// reflect the new state. A refused action (conflict / unauthorized) is shown
	// inline without disturbing the loaded page.
	async function act(name: string, fn: (id: string) => Promise<unknown>) {
		const current = id;
		if (!current || acting) return;
		acting = name;
		actionError = null;
		confirming = null;
		try {
			await fn(current);
			await load(current, { silent: true });
		} catch (e) {
			actionError = e instanceof ApiError ? e : new ApiError('client_error', String(e));
		} finally {
			acting = null;
		}
	}

	// Re-fetch whenever the route id changes.
	$effect(() => {
		const current = id;
		if (!current) return;
		actionError = null;
		confirming = null;
		load(current);
	});

	// Live pulse: while the experiment is dispatching, refresh the activity
	// snapshot every 6s so the heart accumulates a rhythm (surface_liveness_and_
	// activity_view_design.md). The status flips are read inside the tick (not the
	// effect body) so the interval isn't torn down/recreated on every refresh.
	$effect(() => {
		const current = id;
		if (!current) return;
		const tick = async () => {
			const st = experiment?.status;
			// Refetch the experiment/activity only while it's still live — but
			// coordinator health is INDEPENDENT of the experiment's lifecycle, so
			// always probe it (a completed experiment still has a live coordinator).
			if (st !== 'completed' && st !== 'aborted' && st !== 'archived') {
				try {
					activity = await api.getExperimentActivity(current);
					experiment = await api.getExperiment(current);
				} catch {
					/* transient — keep prior */
				}
			}
			// Debounced: a single failed probe (e.g. a ~3s coordinator restart)
			// reads as "reconnecting…", not a red "unreachable" alarm. Only after
			// COORD_FAIL_THRESHOLD consecutive misses do we surface unreachable.
			let ok: boolean;
			try {
				const h = await (await fetch('/api/v0/health')).json();
				ok = h?.coord?.reachable !== false;
			} catch {
				ok = false;
			}
			if (ok) {
				coordReachable = true;
				coordReconnecting = false;
				coordFails = 0;
			} else if (++coordFails >= COORD_FAIL_THRESHOLD) {
				coordReachable = false;
				coordReconnecting = false;
			} else {
				coordReconnecting = true; // keep the last reachable value; don't alarm yet
			}
		};
		tick(); // immediate — no 6s window of unknown coordinator status
		const interval = setInterval(tick, 6000);
		return () => clearInterval(interval);
	});

	// Load results on route change or when the consensus/raw toggle flips.
	$effect(() => {
		const current = id;
		const include = resultsInclude;
		if (!current) return;
		exportMsg = null;
		loadResults(current, include, { reset: true });
	});

	const counts = $derived(workUnits?.counts_by_status ?? {});
	const totalUnits = $derived(Object.values(counts).reduce((a, b) => a + b, 0));

	// Researcher-actionable transitions, gated on the coordinator's transition
	// map (approve/archive are maintainer-only and intentionally absent). These
	// `can*` predicates are the source-of-truth ENABLE conditions — they mirror
	// the coordinator, so a disabled action clicked anyway would come back 409.
	const status = $derived(experiment?.status);

	// Certification provenance (§6.7), parsed from the assessment rationale the
	// coordinator denormalized onto the experiment. Gives the researcher a one-click
	// path to the PUBLIC proof (the Rekor entry) — verifiable without trusting us.
	const certifiedAnchor = $derived.by(() => {
		const r = experiment?.assessment_rationale ?? '';
		if (!/· certified /.test(r)) return null;
		return {
			profile: r.match(/· certified (\S+)/)?.[1] ?? null,
			logIndex: r.match(/Rekor logIndex (\d+)/)?.[1] ?? null
		};
	});
	const canPause = $derived(status === 'approved');
	const canResume = $derived(status === 'paused');
	const canFinalize = $derived(
		(status === 'approved' || status === 'paused') && !experiment?.submissions_finalized
	);
	const canAbort = $derived(status === 'submitted' || status === 'approved' || status === 'paused');

	// Terminal experiments will never be actionable again, so we hide the bar
	// entirely — a row of permanently-dead buttons is noise. Non-terminal states
	// show all four actions in a fixed order (stable layout), disabling the
	// currently-inapplicable ones with a reason so the lifecycle vocabulary stays
	// discoverable instead of appearing only once the right state is reached.
	const terminal = $derived(
		status === 'completed' || status === 'aborted' || status === 'archived'
	);

	// Why a disabled action is unavailable — surfaced inline on the button (and
	// as its title). Only read on the `{:else}` branch, i.e. when the matching
	// `can*` is false, so each need only explain its own not-enabled states.
	const pauseReason = $derived(status === 'paused' ? 'already paused' : 'only while approved');
	const resumeReason = $derived(status === 'approved' ? 'after pausing' : 'only while paused');
	const finalizeReason = $derived(
		experiment?.submissions_finalized ? 'already finalized' : 'available once approved'
	);
	const abortReason = 'not available in this state';
</script>

<p class="back"><a href="/experiments">← My Experiments</a></p>

{#if loading}
	<p class="muted">Loading…</p>
{:else if error}
	<ErrorState {error} />
{:else if experiment}
	<div class="head">
		<h1>{experiment.tenant_experiment_label ?? experiment.experiment_id}</h1>
		<StatusBadge status={experiment.status} />
		<!-- D12: 'approved' is overloaded for queued-vs-running. When the run is
		     approved but not yet started (no worker has picked it up), show a
		     glanceable queued badge with its place in line; the liveness-note below
		     explains *why* it's waiting. Amber 'warn' tone = a waiting state, not a
		     fault. -->
		{#if activity?.run_phase === 'queued'}
			<span class="badge warn" title="Approved, but not running yet — waiting for an available worker."
				>queued{#if activity.queue_position && activity.queue_depth}
					· {activity.queue_position}/{activity.queue_depth} in line{/if}</span
			>
		{/if}
	</div>
	<p class="id">{experiment.experiment_id}</p>

	<LifecycleTimeline {experiment} {activity} />

	<ActivityHeart {experiment} {activity} {coordReachable} {coordReconnecting} />

	<!-- D8 "liveness note": a paused/stalled run self-explains here — most
	     importantly, a C14 regime-3 pause reads as a "waiting for an eligible
	     worker, auto-resumes" hold rather than a silent stall. Only rendered
	     when the coordinator has something to explain. Amber/attention tone. -->
	{#if activity?.liveness_note}
		<p class="liveness-note">{activity.liveness_note}</p>
	{/if}

	<!-- D12 Inc 5: queued-capacity detail — the busy/idle ratio (5a) and a
	     model-download progress bar (5c). The liveness-note above carries the
	     prose; these add the glanceable numbers. Only while queued. -->
	{#if activity?.run_phase === 'queued'}
		{#if activity.capable_worker_count != null}
			<p style="font-size: 0.78rem; color: #9aa3b8; margin: 0.2rem 0;">
				{activity.capable_busy_count ?? 0} of {activity.capable_worker_count} eligible
				worker{activity.capable_worker_count === 1 ? '' : 's'} busy
			</p>
		{/if}
		{#if activity.download_progress}
			<div style="margin: 0.25rem 0; max-width: 320px;">
				<div style="font-size: 0.78rem; color: #9aa3b8; margin-bottom: 0.2rem;">
					downloading model{activity.download_progress.pct != null
						? ` · ${activity.download_progress.pct}%`
						: '…'}
				</div>
				{#if activity.download_progress.pct != null}
					<div style="height: 6px; background: #1a2236; border-radius: 999px; overflow: hidden;">
						<div
							style="height: 100%; width: {activity.download_progress
								.pct}%; background: linear-gradient(90deg, #155e6b, #67e8f9);"
						></div>
					</div>
				{/if}
			</div>
		{/if}
	{/if}

	<!-- A state-unavailable action: shown disabled with the reason it's not
	     usable yet, so the full lifecycle vocabulary stays discoverable. -->
	{#snippet unavailable(label: string, reason: string, variant: string)}
		<button class="act {variant}" disabled title="Unavailable — {reason}.">
			{label}<span class="why"> — {reason}</span>
		</button>
	{/snippet}

	<nav class="tabs" aria-label="Experiment sections">
		<button class="tab" class:active={tab === 'progress'} onclick={() => (tab = 'progress')}>Progress</button>
		<button class="tab" class:active={tab === 'evidence'} onclick={() => (tab = 'evidence')}>Evidence</button>
		<button class="tab" class:active={tab === 'export'} onclick={() => (tab = 'export')}>Export</button>
	</nav>

	{#if tab === 'progress'}
	{#if terminal}
		<p class="no-actions">No actions available — experiment is {experiment.status}.</p>
	{:else}
		<div class="actions">
			{#if canPause}
				<button class="act" onclick={() => act('pause', api.pauseExperiment)} disabled={!!acting}>
					{acting === 'pause' ? 'Pausing…' : 'Pause'}
				</button>
			{:else}
				{@render unavailable('Pause', pauseReason, '')}
			{/if}

			{#if canResume}
				<button class="act" onclick={() => act('resume', api.resumeExperiment)} disabled={!!acting}>
					{acting === 'resume' ? 'Resuming…' : 'Resume'}
				</button>
			{:else}
				{@render unavailable('Resume', resumeReason, '')}
			{/if}

			{#if canFinalize}
				{#if confirming === 'finalize'}
					<span class="confirm">
						Finalize submissions? No more work units can be added afterward.
						<button class="act danger" onclick={() => act('finalize', api.finalizeExperiment)} disabled={!!acting}>
							{acting === 'finalize' ? 'Finalizing…' : 'Confirm'}
						</button>
						<button class="act ghost" onclick={() => (confirming = null)} disabled={!!acting}>Cancel</button>
					</span>
				{:else}
					<button class="act" onclick={() => (confirming = 'finalize')} disabled={!!acting}>
						Finalize submissions
					</button>
				{/if}
			{:else}
				{@render unavailable('Finalize submissions', finalizeReason, '')}
			{/if}

			{#if canAbort}
				{#if confirming === 'abort'}
					<span class="confirm">
						Abort this experiment? This cannot be undone.
						<button class="act danger" onclick={() => act('abort', api.abortExperiment)} disabled={!!acting}>
							{acting === 'abort' ? 'Aborting…' : 'Confirm abort'}
						</button>
						<button class="act ghost" onclick={() => (confirming = null)} disabled={!!acting}>Cancel</button>
					</span>
				{:else}
					<button class="act danger-outline" onclick={() => (confirming = 'abort')} disabled={!!acting}>
						Abort
					</button>
				{/if}
			{:else}
				{@render unavailable('Abort', abortReason, 'danger-outline')}
			{/if}
		</div>
		{#if actionError}
			<p class="action-error" class:conflict={actionError.kind === 'conflict'}>{actionError.message}</p>
		{/if}
	{/if}

	<section class="grid">
		<div class="field"><span class="k">Submitted</span><span class="v">{fmt(experiment.submitted_at)}</span></div>
		<div class="field"><span class="k">Started</span><span class="v">{fmt(experiment.started_at)}</span></div>
		<div class="field"><span class="k">Completed</span><span class="v">{fmt(experiment.completed_at)}</span></div>
		<div class="field"><span class="k">Submissions</span><span class="v">{experiment.submissions_finalized ? 'finalized' : 'open'}</span></div>
		<div class="field"><span class="k">Integrity policy</span><span class="v">{experiment.integrity_policy ?? '—'}</span></div>
		<div class="field"><span class="k">Revision</span><span class="v">{experiment.revision ?? '—'}</span></div>
		{#if experiment.last_action_at}
			<div class="field">
				<span class="k">Last action</span>
				<span class="v">{fmt(experiment.last_action_at)} · {experiment.last_action_by_class ?? '—'}</span>
			</div>
		{/if}
		{#if experiment.manifest_hash}
			<div class="field wide">
				<span class="k">Manifest hash</span><span class="v mono">{experiment.manifest_hash}</span>
			</div>
		{/if}
	</section>
	{/if}

	{#if tab === 'evidence'}
	<h2>Integrity</h2>
	<p class="muted">
		<strong>What this means:</strong> the apparatus's own disclosures about how this
		experiment's evidence was produced — corroboration basis, containment, and producer
		independence. Use them to <em>stratify, don't pool</em>: a process-only result and a
		consensus-replicated one are different evidence classes. Divergence is recorded, never
		penalized — it can be the finding. Full guide:
		<a
			href="https://github.com/auspexai/tenant-sdk/blob/main/docs/reading_your_evidence.md"
			target="_blank"
			rel="noopener">Reading your evidence</a
		>.
	</p>
	{#if certifiedAnchor}
		<div class="cert-badge">
			<span class="cert-check" aria-hidden="true">✓</span>
			<div>
				<strong>Certified profile</strong>{#if certifiedAnchor.profile}
					— {certifiedAnchor.profile}{/if}. A vetted, signed starter; its admission was a
				standing approval, not a per-run review.
				{#if certifiedAnchor.logIndex}
					<a
						href={certifiedAnchor.profile
							? `https://auspexai.network/verify.html?profile=${encodeURIComponent(certifiedAnchor.profile)}`
							: 'https://auspexai.network/verify.html'}
						target="_blank"
						rel="noopener noreferrer"
						title="open the public verifier — checks signature, signer roster, and Rekor inclusion"
						>Verify this certificate (Rekor {certifiedAnchor.logIndex}) ↗</a
					>
				{/if}
			</div>
		</div>
	{/if}
	{#if attestationLoading}
		<p class="muted">Loading attestation…</p>
	{:else if attestation}
		<p class="att-status" class:partial={attestation.partial}>
			{#if attestation.partial}
				Checkpoint attestation — partial, over the consensus-so-far set. The final
				attestation is issued when the experiment completes.
			{:else}
				Final result-set attestation — persisted and canonical. The signed merkle root
				covers every consensus unit; your evidence bundle verifies against it.
			{/if}
		</p>
		<section class="grid">
			<div class="field">
				<span class="k">Attestation</span>
				<span class="v mono">{attestation.attestation_id ?? '— (checkpoint, unpersisted)'}</span>
			</div>
			<div class="field">
				<span class="k">Algorithm · units</span>
				<span class="v">{attestation.algorithm ?? '—'} · {attestation.unit_count ?? 0}</span>
			</div>
			<div class="field">
				<span class="k">Rekor anchor</span>
				<span class="v">
					{#if attestation.rekor_log_index != null}
						<a
							class="rekor"
							href="https://search.sigstore.dev/?logIndex={attestation.rekor_log_index}"
							target="_blank"
							rel="noopener noreferrer"
							title="View this attestation's entry in the public Sigstore transparency log."
						>log index {attestation.rekor_log_index} ↗</a>
						{#if attestation.rekor_inclusion_proof}
							<span class="proof" title="The RFC 6962 inclusion proof is captured in your evidence bundle for offline verification.">inclusion proof captured</span>
						{/if}
					{:else if attestation.partial}
						<span class="muted">checkpoints are not anchored</span>
					{:else}
						<span class="pending">not yet anchored — the hourly transparency-log sweep is pending</span>
					{/if}
				</span>
			</div>
			<div class="field">
				<span class="k">Coordinator signing key</span>
				<span class="v mono">{attestation.signing_key_pubkey_hex ? `${attestation.signing_key_pubkey_hex.slice(0, 16)}…` : '—'}</span>
			</div>
			<div class="field wide">
				<span class="k">Merkle root</span>
				<span class="v mono">{attestation.merkle_root ?? '—'}</span>
			</div>
			{#if attestation.governance_footprint}
				{@const fp = attestation.governance_footprint}
				{@const present = Object.entries(fp.integrity_basis?.counts ?? {}).filter(([, n]) => Number(n) > 0)}
				<div class="footprint">
					<h3>Apparatus footprint</h3>
					<p class="muted small">
						The governance conditions behind this evidence — so you can correct for apparatus
						influence. Coordinator-asserted, COSE-signed in the predicate.
					</p>
					<div class="field">
						<span
							class="k"
							title="Tier = the tenant's trust level (T0–T3). Identity gate = how that tenant authenticated."
							>Producing tenant</span
						>
						<span class="v">tier {fp.tenant?.tier ?? '—'} · identity {fp.tenant?.identity_gate ?? '—'}</span>
					</div>
					<div class="field">
						<span
							class="k"
							title="Replication policy: trusted = 1 worker per unit, standard = 3, high = 5. The factor is how many independent workers corroborated each unit."
							>Replication</span
						>
						<span class="v">
							{fp.replication?.integrity_policy ?? '—'} (×{fp.replication?.replication_factor ?? '—'})
							{#if fp.replication?.sub_floor}<span class="badge warn">below tier floor (forced)</span
								>{:else if fp.replication?.tier_floored}<span class="badge">at tier floor</span
								>{/if}
						</span>
					</div>
					{#if fp.generation}
						<div class="field">
							<span
								class="k"
								title="The generation policy the signed manifest declared. greedy = byte-deterministic decoding (replicas should match). seeded sampling = declared temperature with a pinned seed (replicas legitimately differ — each is an independent sample, so read divergence as the design, not a fault)."
								>Generation policy</span
							>
							<span class="v">
								{fp.generation.mode === 'seeded_sampling' ? 'seeded sampling' : (fp.generation.mode ?? '—')}
								{#if fp.generation.params}
									· {Object.entries(fp.generation.params)
										.map(([k, v]) => `${k}=${v}`)
										.join(' · ')}
								{/if}
							</span>
						</div>
					{/if}
					<div class="field">
						<span
							class="k"
							title="The experiment's declared research class and how it was approved (auto vs. who set the tenant tier)."
							>Approval path</span
						>
						<span class="v">
							experiment <span title={glossOf(APPROVAL_GLOSS, fp.approval?.experiment)}
								>{fp.approval?.experiment ?? '—'}</span
							>{#if fp.approval?.assessment?.research_class}
								· {humanize(fp.approval.assessment.research_class)}{/if}{#if fp.approval?.promotion?.tier_set_by}
								· promotion by {fp.approval.promotion.tier_set_by}{/if}
						</span>
					</div>
					<div class="field">
						<span
							class="k"
							title="How producer-independence was counted — by distinct ACCOUNTS, not just workers, so one operator running many workers can't inflate it."
							>Independence ({fp.independence?.basis ?? '—'})</span
						>
						<span class="v"
							>{fp.independence?.distinct_accounts ?? 0} accounts · {fp.independence
								?.distinct_workers ?? 0} workers · {fp.independence?.distinct_served_models ?? 0} models</span
						>
					</div>
					<div class="field wide">
						<span class="k">Corroboration basis</span>
						<span class="v badges">
							{#each present as [basis, n]}
								<span class="badge" class:diverged={basis === 'diverged'} title={BASIS_GLOSS[basis] ?? ''}
									>{basisLabel(basis)}: {n}</span
								>
							{/each}
						</span>
						{#if present.length}
							<span class="basis-gloss">
								{#each present as [basis]}<span class="bg-item"
										><strong>{basisLabel(basis)}</strong> — {BASIS_GLOSS[basis] ?? ''}</span
									>{/each}
							</span>
						{/if}
					</div>
					<div class="field wide">
						<span
							class="k"
							title="The sandbox the apparatus REQUIRED for this experiment vs the policies the corroborating workers actually RAN UNDER. strict = hardened kernel sandbox (seccomp syscall filter + namespaces + cgroup caps); permissive = ordinary OS process isolation."
							>Containment</span
						>
						<span class="v"
							>required <strong title={glossOf(CONTAINMENT_GLOSS, fp.containment?.required)}
								>{fp.containment?.required ?? '—'}</strong
							> · ran under {(fp.containment?.ran_under ?? []).join(', ') || '—'}</span
						>
					</div>
				</div>
			{/if}
		</section>
	{:else if attestationError && attestationError.kind !== 'not_ready'}
		<p class="muted">Attestation unavailable: {attestationError.message}</p>
	{:else if experiment.status === 'completed'}
		<p class="muted">No attestation available for this experiment.</p>
	{:else}
		<p class="muted">
			The final result-set attestation is issued when the experiment completes.
			{#if status === 'running' || status === 'approved' || status === 'paused'}
				You can anchor a partial integrity checkpoint over the consensus-so-far set now:
			{/if}
		</p>
		{#if status === 'running' || status === 'approved' || status === 'paused'}
			<button
				class="act"
				onclick={() => id && loadAttestation(id, { checkpoint: true })}
				disabled={attestationLoading}
				title="Build a checkpoint attestation over the units that have reached consensus so far. Tamper-evident even mid-run."
			>
				Build checkpoint attestation
			</button>
		{/if}
	{/if}

	<div class="custody" class:held={!!experiment.results_collected_at}>
		{#if experiment.results_collected_at}
			<p class="custody-line ok">
				You hold the durable copy — collected {fmt(experiment.results_collected_at)}.
				Server-side payloads age off after collection; your bundle is the record.
			</p>
			<p class="custody-cmd">
				Re-verify it offline anytime: <code>auspexai-tenant bundle verify &lt;bundle.json&gt;</code>
			</p>
		{:else}
			<p class="custody-line">
				The coordinator’s copy of these results is subject to age-off — be sure you’ve downloaded your evidence bundle (Results below, or <code>auspexai-tenant experiment export</code>) to keep the durable record.
			</p>
		{/if}
		{#if experiment.retention_hold}
			<p class="custody-hold" title="A maintainer placed a retention hold — the age-off sweep skips this experiment.">
				retention hold active — age-off paused
			</p>
		{/if}
	</div>

	{#if experiment.status === 'completed' && citation}
		<section class="cite">
			<h2>Cite this work</h2>
			<p class="muted cite-intro">
				When your analysis is done and you're ready to publish, this credits the compute
				behind the result. Volunteers who opted into public attribution appear by name;
				everyone else is aggregated anonymously. A DOI for the result is coming.
			</p>
			<div class="cite-ack">
				<code>{citation.acknowledgment}</code>
				<button
					class="act"
					onclick={() => {
						if (citation?.acknowledgment) {
							navigator.clipboard?.writeText(citation.acknowledgment);
							citeCopied = true;
						}
					}}
					title="Copy the acknowledgment line"
				>
					{citeCopied ? 'Copied ✓' : 'Copy'}
				</button>
			</div>
		</section>
	{/if}
	{/if}

	{#if tab === 'progress'}
	<!-- The headline activity numbers (contributors, replication fill, work
	     units, network size, last beat) now live in the ActivityHeart above.
	     What remains here is the drill-down the heart doesn't show: the
	     researcher's OWN-account workers backing this experiment. Most
	     researchers run none, so the section simply isn't there for them. -->
	{#if activity?.own_workers && activity.own_workers.length > 0}
		{@const backing = activity.own_workers.filter(
			(w) => w.experiment_eligibility === 'backing'
		).length}
		<h2>Your workers</h2>
		<p class="muted">
			{backing} of your {activity.own_workers.length} account {activity.own_workers.length === 1
				? 'worker is'
				: 'workers are'} backing this experiment; the rest are shown with why they aren't
			(other contributors are anonymized). Live worker status is on the
			<a class="inline-link" href="/">Overview</a>.
		</p>
			<table class="workers">
				<thead>
					<tr><th>Worker</th><th>Tier</th><th>This experiment</th><th>Results</th><th>Last activity</th></tr>
				</thead>
				<tbody>
					{#each activity.own_workers as w (w.worker_id)}
						<tr>
							<td>
								<span class="wid">{w.worker_id}</span>
								<span class="mono pk">{w.worker_pubkey_hex.slice(0, 16)}…</span>
							</td>
							<td>T{w.trust_tier}</td>
							<td>
								<span class="elig elig-{w.experiment_eligibility ?? 'eligible'}"
									>{w.experiment_eligibility ?? 'eligible'}</span
								>
								{#if w.experiment_eligibility === 'ineligible' && w.experiment_ineligible_reason}
									<div class="reason" title="Why this worker can't serve this experiment.">
										{w.experiment_ineligible_reason}
									</div>
								{/if}
							</td>
							<td>{w.result_count}</td>
							<td class="muted">{fmt(w.last_activity_at)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
	{/if}

	<h2>Work units</h2>
	{#if totalUnits === 0}
		<p class="muted">No work units submitted yet.</p>
	{:else}
		<p class="muted">{totalUnits} total</p>
		<div class="counts">
			{#each Object.entries(counts) as [status, n] (status)}
				<div class="count">
					<span class="n">{n}</span>
					<StatusBadge {status} />
				</div>
			{/each}
		</div>
	{/if}

	<!-- Richer D8: live corroboration health. The cross-check status as it
	     happens — whether replicas are agreeing or diverging — so a researcher
	     sees it live, not only retrospectively in the evidence footprint. A
	     diverged unit's replicas disagreed (nondeterminism or a model/version
	     skew), which earns no agreement and no receipt; it is recorded, not
	     model drift. The 0-state is shown calmly on purpose — clean corroboration
	     is the reassurance. -->
	{#if activity?.diverged_unit_count != null}
		{@const diverged = activity.diverged_unit_count}
		<h2>Corroboration</h2>
		<div class="counts">
			<div class="count">
				<span class="n">{counts.completed ?? 0}</span>
				<span class="corr-label">completed</span>
			</div>
			<div class="count">
				<span class="n">{counts.in_progress ?? 0}</span>
				<span class="corr-label">in progress</span>
			</div>
			<div class="count corr-diverged" class:alert={diverged > 0}>
				<span class="n">{diverged}</span>
				<span class="corr-label">diverged</span>
			</div>
		</div>
		{#if diverged > 0}
			<p class="corr-gloss alert">
				{diverged}
				{diverged === 1 ? "unit's" : "units'"} replicas disagreed — nondeterminism or a model/version
				skew, not model drift.
			</p>
		{:else}
			<p class="corr-gloss ok">0 diverged — corroboration clean.</p>
		{/if}
	{/if}
	{/if}

	{#if tab === 'export'}
	<h2>Results</h2>
	<div class="results-head">
		<div class="toggle">
			<button
				class="seg"
				class:active={resultsInclude === 'consensus'}
				onclick={() => (resultsInclude = 'consensus')}
			>Consensus</button>
			<button
				class="seg"
				class:active={resultsInclude === 'raw'}
				onclick={() => (resultsInclude = 'raw')}
			>All replicas</button>
		</div>
		<button
			class="act"
			onclick={doExport}
			disabled={exporting}
			title="Download the full offload bundle (results + receipts + manifest + signed custody record). Collecting transfers data custody to you."
		>
			{exporting ? 'Collecting…' : 'Download bundle'}
		</button>
	</div>
	{#if experiment?.results_collected_at}
		<p class="muted collected">
			Collected {fmt(experiment.results_collected_at)} — data custody transferred to you.
		</p>
	{/if}
	<p class="analyze-hint">
		Have your bundle? <a href="/reference">Reference › Understand your results</a> — how to read it,
		what every <code>output.*</code> column means, and the analysis recipes.
	</p>
	{#if exportMsg}
		<p class="export-msg">{exportMsg}</p>
	{/if}
	{#if verification}
		<div class="verification" class:bad={!verification.ok}>
			<p class="verif-head">
				<span class="vmark">{verification.ok ? '✓' : '✗'}</span>
				{verification.ok ? 'Verified on this machine' : 'Verification FAILED'}
			</p>
			{#if verification.error}<p class="verif-err">{verification.error}</p>{/if}
			<ul class="verif-checks">
				{#each verification.checks as c (c.name)}
					<li class="vcheck {c.state}">
						<span class="vmark">{c.state === 'pass' ? '✓' : c.state === 'fail' ? '✗' : '–'}</span>
						<span class="vname">{c.name}</span>
						{#if c.detail}<span class="vdetail">{c.detail}</span>{/if}
					</li>
				{/each}
				<li class="vcheck {verification.rekor.state === 'anchored' ? 'pass' : 'na'}">
					<span class="vmark">{verification.rekor.state === 'anchored' ? '✓' : '⧖'}</span>
					<span class="vname">Rekor anchor</span>
					<span class="vdetail"
						>{verification.rekor.state === 'anchored'
							? `logIndex ${verification.rekor.log_index}`
							: 'pending — lands on the hourly Rekor sweep'}</span
					>
				</li>
			</ul>
			<p class="verif-foot">
				Verified locally by the SDK on this machine. Reproduce it independently anytime:
				<code>auspexai-tenant bundle verify {id}-bundle.json</code>
			</p>
		</div>
	{/if}
	{#if resultsError}
		<p class="muted">Results unavailable: {resultsError.message}</p>
	{:else if results === null && resultsLoading}
		<p class="muted">Loading results…</p>
	{:else if results && results.length === 0}
		<p class="muted">No results yet — they appear as work units reach consensus.</p>
	{:else if results}
		<table class="results-tbl">
			<thead>
				<tr><th>Unit</th><th>Result</th><th>Payload</th><th>Receipt</th></tr>
			</thead>
			<tbody>
				{#each results as r (r.result_id)}
					<tr>
						<td class="mono">
							{r.unit_id}
							{#if r.is_consensus}<span class="tag">consensus</span>{/if}
							{#if r.is_consensus && r.consensus_evidence}
								<div class="tol muted" title={tolDetail(r.consensus_evidence)}>
									{tolSummary(r.consensus_evidence)}
								</div>
							{/if}
						</td>
						<td class="mono pk">{r.result_id}</td>
						<td>
							{#if r.aged_off}
								<span
									class="aged"
									title="Payload aged off coordinator-side; the receipt + hash still prove it ran."
								>aged off</span>
							{:else if r.payload}
								<code class="payload">{JSON.stringify(r.payload).slice(0, 100)}</code>
							{:else}
								<span class="muted">—</span>
							{/if}
						</td>
						<td class="mono pk">{r.receipt_id ?? '—'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#if resultsCursor}
			<button
				class="act ghost more"
				onclick={() => id && loadResults(id, resultsInclude)}
				disabled={resultsLoading}
			>
				{resultsLoading ? 'Loading…' : 'Load more'}
			</button>
		{/if}
	{/if}
	{/if}

	{#if tab === 'evidence'}
	<h2>Receipts</h2>
	{#if receipts === null}
		<p class="muted">Receipts unavailable.</p>
	{:else if receipts.length === 0}
		<p class="muted">No receipts issued yet — they appear as volunteers complete work.</p>
	{:else}
		<p class="muted">{receipts.length} issued</p>
		{#if attestation?.rekor_log_index}
			<p class="muted receipts-anchor">
				Each receipt is a leaf under this experiment's result-set attestation, anchored at
				<a
					class="rekor"
					href="https://search.sigstore.dev/?logIndex={attestation.rekor_log_index}"
					target="_blank"
					rel="noopener noreferrer">Rekor log index {attestation.rekor_log_index} ↗</a
				> — so any receipt here is provably part of that transparency-logged set.
			</p>
		{/if}
		<table class="receipts">
			<thead>
				<tr><th>Receipt</th><th>Issued</th></tr>
			</thead>
			<tbody>
				{#each receipts as r (r.receipt_id)}
					<tr>
						<td class="mono">{r.receipt_id}</td>
						<td class="muted">{fmt(r.issued_at)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
	{/if}
{/if}

<style>
	.back {
		margin: 0 0 0.5rem;
	}
	.back a {
		color: #8b93a7;
		text-decoration: none;
		font-size: 0.85rem;
	}
	.back a:hover {
		color: #b8bfd0;
	}
	.tabs {
		display: flex;
		gap: 0.25rem;
		border-bottom: 1px solid #1e2638;
		margin: 1rem 0 1.25rem;
	}
	.tab {
		background: none;
		border: none;
		border-bottom: 2px solid transparent;
		color: #8b93a7;
		font: inherit;
		font-size: 0.9rem;
		padding: 0.5rem 0.9rem;
		cursor: pointer;
	}
	.tab:hover {
		color: #cdd5e6;
	}
	.tab.active {
		color: #e6e9f0;
		border-bottom-color: #4a7dff;
	}
	.head {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	h1 {
		font-weight: 700;
		margin: 0;
	}
	.id {
		font-family: ui-monospace, monospace;
		font-size: 0.75rem;
		color: #6b7390;
		margin: 0.25rem 0 0;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin: 1rem 0 0;
	}
	.act {
		font: inherit;
		font-size: 0.82rem;
		padding: 0.4rem 0.8rem;
		border-radius: 6px;
		border: 1px solid #2a3550;
		background: #141b2c;
		color: #e6e9f0;
		cursor: pointer;
	}
	.act:hover:not(:disabled) {
		border-color: #4a7dff;
	}
	.act:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	/* The inline reason on a state-unavailable action. */
	.why {
		font-style: italic;
		font-weight: 400;
	}
	/* Terminal experiments: a single muted line in place of the action bar. */
	.no-actions {
		margin: 1rem 0 0;
		font-size: 0.83rem;
		color: #6b7390;
	}
	.act.danger {
		border-color: #b4434f;
		background: #b4434f;
		color: #fff;
	}
	.act.danger:hover:not(:disabled) {
		border-color: #d05561;
		background: #d05561;
	}
	.act.danger-outline {
		border-color: #7a2e36;
		background: transparent;
		color: #f7a6ad;
	}
	.act.danger-outline:hover:not(:disabled) {
		border-color: #b4434f;
		background: #b4434f;
		color: #fff;
	}
	.act.ghost {
		background: transparent;
		border-color: #2a3550;
		color: #8b93a7;
	}
	.confirm {
		display: inline-flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.5rem;
		font-size: 0.82rem;
		color: #cbd2e0;
		background: #0e1424;
		border: 1px solid #2a3550;
		border-radius: 6px;
		padding: 0.35rem 0.6rem;
	}
	.action-error {
		margin: 0.6rem 0 0;
		font-size: 0.83rem;
		color: #f7a6ad;
	}
	/* A conflict is an expected "can't do that from this state" refusal — amber,
	   not the red reserved for transport/auth failures. */
	.action-error.conflict {
		color: #fbbf24;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.75rem;
		margin: 1.25rem 0;
	}
	.field {
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.6rem 0.8rem;
		background: #0e1424;
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
	}
	.field.wide {
		grid-column: 1 / -1;
	}
	.k {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
	}
	.v {
		color: #e6e9f0;
		font-size: 0.9rem;
	}
	.v.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.78rem;
		word-break: break-all;
		color: #b8bfd0;
	}
	h2 {
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: #8b93a7;
		margin: 1.5rem 0 0.5rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	/* D8 liveness note — amber/attention banner explaining a paused or
	   thin-corroboration run (matches the page's amber accent: #fbbf24 on a
	   dark amber-tinted surface, like .badge.warn). */
	.liveness-note {
		margin: 0.75rem 0 0;
		padding: 0.6rem 0.85rem;
		border: 1px solid #5a4420;
		border-radius: 6px;
		background: #3a2a18;
		color: #fbbf24;
		font-size: 0.85rem;
		line-height: 1.4;
	}
	.counts {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		margin-top: 0.5rem;
	}
	.count {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.5rem 0.8rem;
		background: #0e1424;
	}
	.n {
		font-size: 1.25rem;
		font-weight: 700;
		color: #e6e9f0;
	}
	.count .label {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
	}
	/* Richer D8 corroboration panel — reuses the .count card; the diverged card
	   stays calm at 0 and turns amber only when there's a divergence to flag. */
	.corr-label {
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
	}
	.corr-diverged.alert {
		border-color: #5a4020;
		background: #3a2a18;
	}
	.corr-diverged.alert .n {
		color: #fbbf24;
	}
	.corr-diverged.alert .corr-label {
		color: #fbbf24;
	}
	.corr-gloss {
		margin: 0.5rem 0 0;
		font-size: 0.8rem;
	}
	.corr-gloss.ok {
		color: #7fd1a8;
	}
	.corr-gloss.alert {
		color: #fbbf24;
	}
	table.receipts,
	table.workers {
		width: 100%;
		border-collapse: collapse;
		margin-top: 0.5rem;
	}
	table.receipts th,
	table.workers th {
		text-align: left;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #1e2638;
	}
	table.receipts td,
	table.workers td {
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #141b2c;
		font-size: 0.85rem;
		color: #e6e9f0;
	}
	.wid {
		color: #e6e9f0;
	}
	.elig {
		display: inline-block;
		padding: 0.05rem 0.5rem;
		border-radius: 3px;
		font-size: 0.78rem;
	}
	.elig-backing {
		background: #14532d;
		color: #86efac;
	}
	.elig-eligible {
		background: #1e3a5f;
		color: #93c5fd;
	}
	.elig-ineligible {
		background: #3f3f46;
		color: #d4d4d8;
	}
	.pk {
		display: block;
		font-family: ui-monospace, monospace;
		font-size: 0.7rem;
		color: #6b7390;
	}
	.reason {
		margin-top: 0.25rem;
		font-size: 0.74rem;
		color: #fbbf24;
		max-width: 22rem;
	}
	a.inline-link {
		color: #7aa2ff;
		text-decoration: none;
	}
	a.inline-link:hover {
		text-decoration: underline;
	}
	td.mono {
		font-family: ui-monospace, monospace;
		font-size: 0.78rem;
		color: #b8bfd0;
	}
	/* ── Apparatus footprint (firewall #2) ── */
	.cert-badge {
		display: flex;
		align-items: flex-start;
		gap: 0.6rem;
		margin: 0.4rem 0 0.9rem;
		padding: 0.7rem 0.9rem;
		border: 1px solid rgba(16, 185, 129, 0.35);
		background: rgba(16, 185, 129, 0.07);
		border-radius: 8px;
		font-size: 0.9rem;
		line-height: 1.5;
	}
	.cert-badge .cert-check {
		color: #10b981;
		font-weight: 700;
		flex-shrink: 0;
	}
	.cert-badge a {
		display: inline-block;
		margin-top: 0.2rem;
	}
	.footprint {
		/* .footprint is itself a grid ITEM in the parent `.grid`, so it was being
		   squeezed into one auto-fit column and its fields stacked vertically. Span
		   the full parent width first (like `.field.wide`), THEN lay its own fields
		   out in the same auto-fit grid. */
		grid-column: 1 / -1;
		margin-top: 0.9rem;
		padding-top: 0.7rem;
		border-top: 1px solid #2a3142;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.6rem 0.75rem;
	}
	.footprint h3,
	.footprint .small {
		grid-column: 1 / -1;
	}
	.footprint h3 {
		font-size: 0.9rem;
		margin: 0 0 0.2rem;
		color: #cdd5e6;
	}
	.footprint .small {
		font-size: 0.74rem;
		margin: 0 0 0.5rem;
		max-width: 52rem;
	}
	.badges {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem;
	}
	.basis-gloss {
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		margin-top: 0.35rem;
		font-size: 0.74rem;
		color: #8b93a7;
	}
	.basis-gloss strong {
		color: #c4ccdc;
		font-weight: 600;
	}
	/* a glossed label is discoverable — dotted underline + a help cursor */
	.footprint .k[title] {
		cursor: help;
		text-decoration: underline dotted #4a5169;
		text-underline-offset: 2px;
	}
	.badge {
		display: inline-block;
		padding: 0.05rem 0.4rem;
		border-radius: 0.6rem;
		background: #232a3a;
		color: #9fb0d0;
		font-size: 0.72rem;
		border: 1px solid #2f3850;
	}
	.badge.warn {
		background: #3a2a18;
		color: #fbbf24;
		border-color: #5a4020;
	}
	.badge.diverged {
		background: #3a1f2a;
		color: #f3a0bb;
		border-color: #5a2f3f;
	}
	/* ── Local verification panel (verify-on-collect) ── */
	.verification {
		margin: 0.6rem 0 0;
		padding: 0.6rem 0.8rem;
		border: 1px solid #1f5a3a;
		border-radius: 6px;
		background: #0d1a14;
	}
	.verification.bad {
		border-color: #5e1f28;
		background: #1a0e12;
	}
	.verif-head {
		margin: 0 0 0.4rem;
		font-weight: 600;
		font-size: 0.85rem;
		color: #6ee7b7;
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
	}
	.verification.bad .verif-head {
		color: #fca5a5;
	}
	.verif-err {
		margin: 0 0 0.4rem;
		font-size: 0.78rem;
		color: #fca5a5;
	}
	.verif-checks {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.vcheck {
		display: flex;
		align-items: baseline;
		gap: 0.4rem;
		font-size: 0.8rem;
		color: #c4ccdc;
	}
	.vcheck .vmark {
		width: 1rem;
		flex: none;
		text-align: center;
	}
	.vcheck.pass .vmark {
		color: #6ee7b7;
	}
	.vcheck.fail,
	.vcheck.fail .vmark {
		color: #fca5a5;
	}
	.vcheck.na .vmark {
		color: #8b93a7;
	}
	.vdetail {
		color: #8b93a7;
		font-size: 0.74rem;
	}
	.verif-foot {
		margin: 0.5rem 0 0;
		font-size: 0.72rem;
		color: #8b93a7;
	}
	.verif-foot code {
		font-size: 0.72rem;
	}
	/* ── Integrity panel (R-D inc-1) ── */
	.att-status {
		font-size: 0.85rem;
		color: #7fd1a8;
		margin: 0.4rem 0 0.6rem;
		max-width: 56rem;
	}
	.att-status.partial {
		color: #fbbf24;
	}
	a.rekor {
		color: #7aa2ff;
		text-decoration: none;
		font-family: ui-monospace, monospace;
		font-size: 0.8rem;
	}
	a.rekor:hover {
		text-decoration: underline;
	}
	.proof {
		display: block;
		margin-top: 0.2rem;
		font-size: 0.7rem;
		color: #7fd1a8;
	}
	.pending {
		color: #fbbf24;
		font-size: 0.8rem;
	}
	.custody {
		border: 1px solid #1e2638;
		border-left: 3px solid #2a3550;
		border-radius: 6px;
		background: #0e1424;
		padding: 0.6rem 0.8rem;
		margin: 0.75rem 0 0;
	}
	.custody.held {
		border-left-color: #2f6b4d;
	}
	.custody-line {
		margin: 0;
		font-size: 0.83rem;
		color: #b8bfd0;
	}
	.custody-line.ok {
		color: #7fd1a8;
	}
	.custody-cmd {
		margin: 0.35rem 0 0;
		font-size: 0.78rem;
		color: #8b93a7;
	}
	.custody-cmd code {
		font-family: ui-monospace, monospace;
		font-size: 0.74rem;
		color: #b8bfd0;
		background: #141b2c;
		border: 1px solid #1e2638;
		border-radius: 4px;
		padding: 0.1rem 0.35rem;
	}
	.cite {
		margin-top: 1.5rem;
	}
	.cite-intro {
		max-width: 46rem;
	}
	.cite-ack {
		display: flex;
		align-items: center;
		gap: 0.6rem;
		flex-wrap: wrap;
		margin-top: 0.6rem;
	}
	.cite-ack code {
		flex: 1 1 22rem;
		font-family: ui-monospace, monospace;
		font-size: 0.82rem;
		line-height: 1.45;
		color: #b8bfd0;
		background: #141b2c;
		border: 1px solid #1e2638;
		border-radius: 6px;
		padding: 0.55rem 0.7rem;
		word-break: break-word;
	}
	.custody-hold {
		margin: 0.35rem 0 0;
		font-size: 0.74rem;
		color: #fbbf24;
	}
	/* ── Results (R-D5) ── */
	.results-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 0.5rem 0;
	}
	.toggle {
		display: inline-flex;
		border: 1px solid #2a3550;
		border-radius: 6px;
		overflow: hidden;
	}
	.seg {
		font: inherit;
		font-size: 0.78rem;
		padding: 0.35rem 0.7rem;
		background: #0e1424;
		color: #8b93a7;
		border: none;
		cursor: pointer;
	}
	.seg.active {
		background: #1f2a44;
		color: #e6e9f0;
	}
	.collected {
		color: #7fd1a8;
		margin: 0.2rem 0;
	}
	.export-msg {
		font-size: 0.83rem;
		color: #8bd0a8;
		margin: 0.4rem 0;
	}
	.analyze-hint {
		font-size: 0.83rem;
		color: #8b93a7;
		margin: 0.4rem 0;
	}
	.analyze-hint a {
		color: #7aa2ff;
		text-decoration: none;
	}
	.analyze-hint a:hover {
		text-decoration: underline;
	}
	table.results-tbl {
		width: 100%;
		border-collapse: collapse;
		margin-top: 0.5rem;
	}
	table.results-tbl th {
		text-align: left;
		font-size: 0.68rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #8b93a7;
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #1e2638;
	}
	table.results-tbl td {
		padding: 0.4rem 0.6rem;
		border-bottom: 1px solid #141b2c;
		font-size: 0.82rem;
		color: #e6e9f0;
		vertical-align: top;
	}
	.tag {
		display: inline-block;
		margin-left: 0.4rem;
		font-family: system-ui, sans-serif;
		font-size: 0.6rem;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: #7aa2ff;
		background: #16203a;
		border: 1px solid #2a3550;
		border-radius: 4px;
		padding: 0.05rem 0.3rem;
	}
	/* C7 Inc 4: the "how this unit agreed" line under a tolerance consensus tag —
	   calm neutral text (color-discipline: informational, not an alert). */
	.tol {
		font-family: system-ui, sans-serif;
		font-size: 0.68rem;
		margin-top: 0.15rem;
		cursor: help;
	}
	.aged {
		font-size: 0.74rem;
		color: #fbbf24;
	}
	.payload {
		font-family: ui-monospace, monospace;
		font-size: 0.74rem;
		color: #8b93a7;
		word-break: break-all;
	}
	.more {
		margin-top: 0.6rem;
	}
</style>
