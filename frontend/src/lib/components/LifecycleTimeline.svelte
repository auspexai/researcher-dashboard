<script lang="ts">
	import type { Experiment, ExperimentActivity } from '$lib/api';

	// §9 #48 inc 3 — the experiment's transparent journey:
	//   submitted → assessed → approved → provisioning/running → completed
	// DERIVED from status + assessment + activity (no new coordinator status: a
	// `review` decision stays `submitted` server-side; `provisioning`/`running`
	// are sub-phases of `approved` told apart by whether units are flowing yet).
	// Answers, at a glance: where is my experiment, why is it waiting, what next.
	let {
		experiment,
		activity = null
	}: { experiment: Experiment; activity?: ExperimentActivity | null } = $props();

	type State = 'done' | 'current' | 'pending' | 'failed';
	type Step = { label: string; state: State; detail: string };

	const status = $derived(experiment.status ?? 'submitted');
	const decision = $derived(experiment.assessment_decision ?? null);
	const rclass = $derived(experiment.research_class ?? null);
	const completions = $derived(activity?.completions_total ?? 0);

	const aborted = $derived(status === 'aborted' || status === 'archived');
	const completed = $derived(status === 'completed');
	const paused = $derived(status === 'paused');
	const approvedPlus = $derived(['approved', 'running', 'paused', 'completed'].includes(status));

	const steps = $derived.by<Step[]>(() => {
		const submitted: Step = { label: 'Submitted', state: 'done', detail: 'received by the coordinator' };

		let assessed: Step;
		if (decision === 'auto')
			assessed = { label: 'Assessed', state: 'done', detail: `classified ${rclass ?? '—'} → auto-approved` };
		else if (decision === 'review')
			assessed = {
				label: 'Assessed',
				state: approvedPlus ? 'done' : 'current',
				detail: `classified ${rclass ?? '—'} → pending human review`
			};
		else
			assessed = {
				label: 'Assessed',
				state: status === 'submitted' && !aborted ? 'current' : aborted ? 'pending' : 'done',
				detail: 'queued for review'
			};

		const approved: Step = {
			label: 'Approved',
			state: approvedPlus ? 'done' : 'pending',
			detail: approvedPlus
				? 'approved — the network is preparing your experiment'
				: decision === 'review'
					? 'awaiting human review'
					: 'awaiting approval'
		};

		let run: Step;
		if (completed) run = { label: 'Ran', state: 'done', detail: `${completions} units attested` };
		else if (paused) run = { label: 'Paused', state: 'current', detail: 'paused — in-flight results still accepted' };
		else if (approvedPlus && completions > 0)
			run = { label: 'Running', state: 'current', detail: `${completions} units so far` };
		else if (approvedPlus)
			run = {
				label: 'Provisioning',
				state: 'current',
				detail: 'staging the model + confirming worker eligibility'
			};
		else run = { label: 'Run', state: 'pending', detail: 'not started' };

		const last: Step = completed
			? { label: 'Completed', state: 'done', detail: 'evidence ready below' }
			: aborted
				? { label: status === 'archived' ? 'Archived' : 'Aborted', state: 'failed', detail: 'experiment ended without completing' }
				: { label: 'Completed', state: 'pending', detail: '' };

		return [submitted, assessed, approved, run, last];
	});

	const activeDetail = $derived(
		steps.find((s) => s.state === 'current')?.detail ??
			steps.findLast((s) => s.state === 'done' || s.state === 'failed')?.detail ??
			''
	);
</script>

<section class="timeline" aria-label="experiment lifecycle">
	<ol>
		{#each steps as s, i (s.label)}
			<li class="step {s.state}">
				{#if i > 0}<span class="bar" class:filled={s.state === 'done'}></span>{/if}
				<span class="dot"></span>
				<span class="label">{s.label}</span>
			</li>
		{/each}
	</ol>
	{#if activeDetail}<p class="detail">{activeDetail}</p>{/if}
</section>

<style>
	.timeline {
		border: 1px solid #1e2638;
		border-radius: 10px;
		background: #0e1424;
		padding: 0.9rem 1.1rem 0.7rem;
		margin-bottom: 1rem;
	}
	ol {
		display: flex;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.step {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		position: relative;
		gap: 0.4rem;
	}
	.bar {
		position: absolute;
		top: 6px;
		right: 50%;
		width: 100%;
		height: 2px;
		background: #233049;
	}
	.bar.filled {
		background: #155e6b;
	}
	.dot {
		width: 14px;
		height: 14px;
		border-radius: 50%;
		background: #233049;
		border: 2px solid #0e1424;
		z-index: 1;
	}
	.step.done .dot {
		background: #6ee7b7;
	}
	.step.current .dot {
		background: #67e8f9;
		box-shadow: 0 0 0 0 rgba(103, 232, 249, 0.5);
		animation: pulse 1.4s ease-out infinite;
	}
	.step.failed .dot {
		background: #fca5a5;
	}
	@keyframes pulse {
		0% {
			box-shadow: 0 0 0 0 rgba(103, 232, 249, 0.5);
		}
		70% {
			box-shadow: 0 0 0 7px rgba(103, 232, 249, 0);
		}
		100% {
			box-shadow: 0 0 0 0 rgba(103, 232, 249, 0);
		}
	}
	.label {
		font-size: 0.72rem;
		color: #7c849a;
		text-align: center;
	}
	.step.done .label {
		color: #b8bfd0;
	}
	.step.current .label {
		color: #67e8f9;
	}
	.step.failed .label {
		color: #fca5a5;
	}
	.detail {
		margin: 0.6rem 0 0;
		font-size: 0.84rem;
		color: #9aa3b8;
		text-align: center;
	}
</style>
