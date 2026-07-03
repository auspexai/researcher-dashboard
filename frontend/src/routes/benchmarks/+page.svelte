<script lang="ts">
	import { onMount } from 'svelte';
	import { api, type BenchmarkSummary } from '$lib/api';

	// The one-pane-of-glass Drift Benchmark view: every report saved under
	// runs/ (computed from the experiment page or the CLI — same layout),
	// newest first. Every number stays traceable to its evidence pair; the
	// eventual PUBLIC board is a separate, signed publication surface — this
	// pane is the researcher's private aggregation.
	let rows = $state<BenchmarkSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	onMount(async () => {
		try {
			rows = (await api.listBenchmarks()).benchmarks ?? [];
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`);
	const eu = (v: number | null | undefined) => (v == null ? 'n/a' : v.toFixed(2));
	const when = (s: string | undefined) => (s ? s.slice(0, 16).replace('T', ' ') : '—');
</script>

<h1>Drift Benchmarks</h1>
<p class="muted">
	One comparable scale across models and configurations: peak drift in envelope units
	(each declared feature's shift ÷ its calibrated tolerance; 1.0 = the boundary between
	noise and drift), with breadth and the divergence overlays reported separately.
	Every row names its reference — the score is <em>against</em> that experiment's
	signed envelope. Reports are computed on an experiment's Benchmark tab (or via
	<span class="mono">auspexai-tenant benchmark drift</span>) and aggregate here.
</p>

{#if loading}
	<p class="muted">Loading…</p>
{:else if error}
	<p class="warn-text">{error}</p>
{:else if !rows.length}
	<p class="muted">
		No benchmark reports yet — open an experiment's <strong>Benchmark</strong> tab,
		pick a reference, and run one.
	</p>
{:else}
	<table class="bench-board">
		<thead>
			<tr>
				<th>experiment</th>
				<th>reference</th>
				<th class="num">peak (EU)</th>
				<th class="num">breadth</th>
				<th class="num">byte-div</th>
				<th class="num">diverged</th>
				<th>computed</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as r (r.path)}
				<tr>
					<td>
						<a href={`/experiments/${r.observation?.experiment_id}`}>
							{r.observation?.label ?? r.observation?.experiment_id}
						</a>
					</td>
					<td class="muted">{r.reference?.label ?? r.reference?.experiment_id}</td>
					<td class="num mono" class:beyond={r.peak_eu != null && r.peak_eu >= 1}>
						{eu(r.peak_eu)}
					</td>
					<td class="num muted">{pct(r.breadth)}</td>
					<td class="num muted">{pct(r.byte_divergence_rate)}</td>
					<td class="num muted">{r.diverged_units_total ?? '—'}</td>
					<td class="muted">{when(r.computed_at)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="muted small">
		EU values are comparable only against the same reference + envelope; check each
		row's reference before comparing across rows.
	</p>
{/if}

<style>
	.bench-board {
		width: 100%;
		border-collapse: collapse;
		margin: 1rem 0 0.5rem;
		font-size: 0.92rem;
	}
	.bench-board th,
	.bench-board td {
		text-align: left;
		padding: 0.45rem 0.75rem 0.45rem 0;
		border-bottom: 1px solid var(--border, #e6e5e1);
	}
	.bench-board .num {
		text-align: right;
		padding-right: 1.2rem;
	}
	.bench-board .beyond {
		font-weight: 700;
	}
	.mono {
		font-family: var(--mono, ui-monospace, monospace);
	}
	.muted {
		color: var(--muted, #6b6a66);
	}
	.small {
		font-size: 0.85rem;
	}
	.warn-text {
		color: var(--warn, #9a6700);
	}
</style>
