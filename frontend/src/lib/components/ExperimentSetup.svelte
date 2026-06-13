<script lang="ts">
	import { onMount } from 'svelte';
	import {
		api,
		ApiError,
		type LocalStatus,
		type ExperimentConfigTables,
		type ExecResult,
		type RunStatus
	} from '$lib/api';

	// §8 browser-driven stand-up, Layer 2: edit the workspace experiment.toml
	// from the browser so there's no text file to hand-author. The form is the
	// dashboard's first surface that writes the researcher's OWN machine — it
	// only appears when WORKSPACE_DIR is set; otherwise we show the CLI flow.
	// Layer 3 (Build/Submit/Run buttons) hangs off `status.exec_enabled` later.

	let status = $state<LocalStatus | null>(null);
	let loadError = $state<string | null>(null);
	let open = $state(false);

	let form = $state({
		label: '',
		tenant_id: '',
		contact: '',
		model_id: '',
		model_version: '1.0',
		local_weights_required: true,
		replication: 1,
		duration_hours: 1,
		research_goal: '',
		prompt_characteristics: '',
		sensitive_flags: '',
		command: 'python executor.py',
		reducer_kind: 'builtin_hash_agreement',
		entrypoint: '',
		journal: 'auto'
	});

	let saving = $state(false);
	let saveOk = $state<string | null>(null);
	let saveError = $state<string | null>(null);

	const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));
	const num = (v: unknown, d: number): number => (typeof v === 'number' ? v : d);

	function populate(c: ExperimentConfigTables) {
		const e = c.experiment ?? {};
		const x = c.executor ?? {};
		const r = c.reducer ?? {};
		const d = c.driver ?? {};
		form.label = str(e.label);
		form.tenant_id = str(e.tenant_id);
		form.contact = str(e.contact);
		form.model_id = str(e.model_id);
		form.model_version = str(e.model_version) || '1.0';
		form.local_weights_required = e.local_weights_required !== false; // default true
		form.replication = num(e.replication, 1);
		form.duration_hours = num(e.duration_hours, 1);
		form.research_goal = str(e.research_goal);
		form.prompt_characteristics = str(e.prompt_characteristics);
		form.sensitive_flags = Array.isArray(e.sensitive_content_flags)
			? (e.sensitive_content_flags as string[]).join(', ')
			: '';
		form.command = Array.isArray(x.command)
			? (x.command as string[]).join(' ')
			: 'python executor.py';
		form.reducer_kind = str(r.kind) || 'builtin_hash_agreement';
		form.entrypoint = str(d.entrypoint);
		form.journal = str(d.journal) || 'auto';
	}

	async function refresh() {
		try {
			status = await api.getLocalStatus();
			if (status.workspace_set) {
				const cfg = await api.getLocalConfig();
				if (cfg.present) populate(cfg.config);
			}
		} catch (e) {
			loadError = e instanceof ApiError ? e.message : String(e);
		}
	}

	onMount(refresh);

	const canSave = $derived(form.label.trim().length > 0);

	function buildPayload(): ExperimentConfigTables {
		const exp: Record<string, unknown> = {
			label: form.label.trim(),
			local_weights_required: form.local_weights_required,
			replication: Number(form.replication) || 1,
			duration_hours: Number(form.duration_hours) || 1,
			// always send the flags array (so clearing it sticks); empty = []
			sensitive_content_flags: form.sensitive_flags
				.split(',')
				.map((s) => s.trim())
				.filter(Boolean)
		};
		// Optional strings: omit when blank so a blank never clobbers an existing
		// value (the server merges; unsent keys are kept).
		const optional: [string, string][] = [
			['tenant_id', form.tenant_id],
			['contact', form.contact],
			['model_id', form.model_id],
			['model_version', form.model_version],
			['research_goal', form.research_goal],
			['prompt_characteristics', form.prompt_characteristics]
		];
		for (const [k, v] of optional) if (v.trim()) exp[k] = v.trim();

		const payload: ExperimentConfigTables = { experiment: exp };
		const cmd = form.command.trim().split(/\s+/).filter(Boolean);
		if (cmd.length) payload.executor = { command: cmd };
		if (form.reducer_kind.trim()) payload.reducer = { kind: form.reducer_kind.trim() };
		const driver: Record<string, unknown> = {};
		if (form.entrypoint.trim()) driver.entrypoint = form.entrypoint.trim();
		if (form.journal.trim()) driver.journal = form.journal.trim();
		if (Object.keys(driver).length) payload.driver = driver;
		return payload;
	}

	async function save() {
		saving = true;
		saveOk = null;
		saveError = null;
		try {
			const res = await api.saveLocalConfig(buildPayload());
			saveOk = `Saved ${res.written}`;
			status = await api.getLocalStatus();
		} catch (e) {
			saveError = e instanceof ApiError ? e.message : String(e);
		} finally {
			saving = false;
		}
	}

	// ── Layer 3: build → submit → run (shells the SDK on this machine) ─────────
	// Each is an explicit click (the per-action consent); submit + run, which
	// reach the network / start the hours-long driver, also confirm first. The
	// driver pulse below is the run's live surface (same colour identity as the
	// experiment heart: cyan working · blue idle · green done · red failed).

	let building = $state(false);
	let submitting = $state(false);
	let starting = $state(false);
	let stopping = $state(false);
	let execNote = $state<{ text: string; ok: boolean } | null>(null);
	let execLog = $state(''); // build/submit output, shown until the run takes over
	let run = $state<RunStatus | null>(null);
	let lastLogSize = $state(0);
	let working = $state(false); // log grew since the last poll → driver is active

	const showResult = (verb: string, r: ExecResult) => {
		execNote = { text: `${verb} ${r.ok ? 'ok' : `failed (rc ${r.returncode})`}`, ok: r.ok };
		execLog = [r.stdout, r.stderr].filter(Boolean).join('\n').trim();
	};

	async function doBuild() {
		building = true;
		execNote = null;
		try {
			showResult('build', await api.execBuild());
			status = await api.getLocalStatus();
		} catch (e) {
			execNote = { text: e instanceof ApiError ? e.message : String(e), ok: false };
		} finally {
			building = false;
		}
	}

	async function doSubmit() {
		if (!confirm('Submit creates an experiment on the coordinator. Continue?')) return;
		submitting = true;
		execNote = null;
		try {
			showResult('submit', await api.execSubmit());
		} catch (e) {
			execNote = { text: e instanceof ApiError ? e.message : String(e), ok: false };
		} finally {
			submitting = false;
		}
	}

	async function doRun() {
		if (!confirm('Run starts the driver on THIS machine and keeps issuing rounds for hours. Continue?'))
			return;
		starting = true;
		execNote = null;
		try {
			const r = await api.startRun();
			execNote = { text: `run started (pid ${r.pid})`, ok: true };
			execLog = '';
			await pollRun();
		} catch (e) {
			execNote = { text: e instanceof ApiError ? e.message : String(e), ok: false };
		} finally {
			starting = false;
		}
	}

	async function doStop() {
		if (!confirm('Stop the running driver?')) return;
		stopping = true;
		try {
			await api.stopRun();
			await pollRun();
		} catch (e) {
			execNote = { text: e instanceof ApiError ? e.message : String(e), ok: false };
		} finally {
			stopping = false;
		}
	}

	async function pollRun() {
		try {
			const r = await api.getRun();
			// log growth since the last sample ⇒ the driver is actively working
			working = !!r.running && (r.log_size ?? 0) > lastLogSize;
			lastLogSize = r.log_size ?? 0;
			run = r;
		} catch {
			/* transient — keep the last known state */
		}
	}

	// Poll the run while exec is enabled (cheap GET; the heart wants a steady beat).
	$effect(() => {
		if (!status?.exec_enabled) return;
		pollRun();
		const id = setInterval(pollRun, 2500);
		return () => clearInterval(id);
	});

	type DriverState = 'none' | 'working' | 'idle' | 'done' | 'failed';
	const driver = $derived<DriverState>(
		!run?.present
			? 'none'
			: run.running
				? working
					? 'working'
					: 'idle'
				: run.returncode === 0
					? 'done'
					: 'failed'
	);
	const driverText = $derived(
		{
			none: '',
			working: 'driver issuing rounds…',
			idle: 'between rounds',
			done: 'run complete',
			failed: `run exited (rc ${run?.returncode})`
		}[driver]
	);
</script>

{#if status === null}
	<!-- still probing local-ops; render nothing to avoid a flash of the fallback -->
{:else if !status.workspace_set}
	<!-- No workspace configured → the dashboard stays monitor-only here; show the
	     CLI stand-up flow (the network-native operation it can't host yet). -->
	<div class="standup cli">
		<p class="hd">Stand up an experiment from your workspace</p>
		<pre><code>auspexai-tenant experiment build  pkg/
auspexai-tenant experiment submit pkg/ --key &lt;key&gt;
auspexai-tenant experiment run    latest --key &lt;key&gt; --doorbell</code></pre>
		<p class="muted">
			Set <code>WORKSPACE_DIR</code> (to the dir holding <code>experiment.toml</code> and
			<code>pkg/</code>) to edit the config here instead of by hand.
		</p>
	</div>
{:else}
	<div class="standup">
		<button class="toggle" onclick={() => (open = !open)} aria-expanded={open}>
			<span class="chev" class:open>▸</span>
			Set up an experiment
			<span class="muted ws">{status.workspace}</span>
		</button>
		{#if open}
			<div class="form">
				<p class="note">
					Saving regenerates <code>experiment.toml</code> in your workspace (inline comments
					are not preserved). Then build + submit + run it{status.exec_enabled
						? ' from the buttons below'
						: ' from the CLI'}.
				</p>
				{#if loadError}<p class="err">{loadError}</p>{/if}

				<div class="grid">
					<label
						>Label <span class="req">*</span>
						<input bind:value={form.label} placeholder="my-experiment" /></label
					>
					<label>Tenant ID <input bind:value={form.tenant_id} placeholder="my-lab" /></label>
					<label
						>Contact <input bind:value={form.contact} placeholder="you@lab.org" /></label
					>
					<label>Model ID <input bind:value={form.model_id} placeholder="gemma-3-1b-it-q4" /></label>
					<label>Model version <input bind:value={form.model_version} /></label>
					<label class="check"
						><input type="checkbox" bind:checked={form.local_weights_required} /> Local weights required</label
					>
					<label>Replication <input type="number" min="1" bind:value={form.replication} /></label>
					<label
						>Duration (hours) <input
							type="number"
							min="0"
							step="0.5"
							bind:value={form.duration_hours}
						/></label
					>
				</div>

				<label
					>Research goal <textarea
						bind:value={form.research_goal}
						rows="3"
						placeholder="What this experiment measures (≥50 chars for the manifest)."
					></textarea></label
				>
				<label
					>Prompt characteristics <textarea
						bind:value={form.prompt_characteristics}
						rows="2"
						placeholder="The nature of the prompt set (no raw prompts)."
					></textarea></label
				>
				<label
					>Sensitive content flags <input
						bind:value={form.sensitive_flags}
						placeholder="comma-separated, e.g. jailbreak (blank = none)"
					/></label
				>

				<div class="grid">
					<label>Executor command <input bind:value={form.command} placeholder="python executor.py" /></label>
					<label>Reducer kind <input bind:value={form.reducer_kind} /></label>
					<label>Driver entrypoint <input bind:value={form.entrypoint} placeholder="my_driver:build" /></label>
					<label>Driver journal <input bind:value={form.journal} placeholder="auto" /></label>
				</div>

				<div class="submit-row">
					<button class="save" onclick={save} disabled={saving || !canSave}>
						{saving ? 'Saving…' : 'Save experiment.toml'}
					</button>
					{#if saveOk}<span class="ok">{saveOk}</span>{/if}
					{#if saveError}<span class="err">{saveError}</span>{/if}
				</div>
			</div>
		{/if}

		{#if status.exec_enabled}
			<div class="exec">
				<div class="exec-head">
					<span class="dot {driver}"></span>
					<strong>Run on this machine</strong>
					{#if driverText}<span class="dstate {driver}">{driverText}</span>{/if}
				</div>
				<div class="btn-row">
					<button class="op" onclick={doBuild} disabled={building || !!run?.running}>
						{building ? 'Building…' : 'Build'}
					</button>
					<button class="op" onclick={doSubmit} disabled={submitting || !!run?.running}>
						{submitting ? 'Submitting…' : 'Submit'}
					</button>
					<button class="op go" onclick={doRun} disabled={starting || !!run?.running}>
						{starting ? 'Starting…' : 'Run ▶'}
					</button>
					{#if run?.running}
						<button class="op stop" onclick={doStop} disabled={stopping}>
							{stopping ? 'Stopping…' : 'Stop'}
						</button>
					{/if}
				</div>
				{#if execNote}<p class="exec-note" class:bad={!execNote.ok}>{execNote.text}</p>{/if}
				{#if run?.running || execLog || run?.log_tail}
					<pre class="exec-log"><code
							>{run?.present && (run?.running || !execLog)
								? (run?.log_tail ?? '')
								: execLog}</code
						></pre>
				{/if}
			</div>
		{/if}
	</div>
{/if}

<style>
	.standup {
		border: 1px solid #1e2638;
		border-radius: 8px;
		background: #10182a;
		margin-bottom: 1.25rem;
	}
	.standup.cli {
		padding: 1rem 1.25rem;
	}
	.hd {
		margin: 0 0 0.5rem;
		color: #e6e9f0;
		font-weight: 600;
	}
	pre {
		margin: 0 0 0.5rem;
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
	}
	pre code {
		background: none;
		padding: 0;
		color: #b8e8d8;
		font-size: 0.82rem;
	}
	.muted {
		color: #8b93a7;
		font-size: 0.85rem;
	}
	.toggle {
		width: 100%;
		text-align: left;
		background: none;
		border: none;
		color: #e6e9f0;
		font: inherit;
		font-weight: 600;
		padding: 0.8rem 1.1rem;
		cursor: pointer;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.chev {
		display: inline-block;
		transition: transform 0.12s ease;
		color: #8b93a7;
	}
	.chev.open {
		transform: rotate(90deg);
	}
	.ws {
		margin-left: auto;
		font-family: ui-monospace, monospace;
		font-weight: 400;
	}
	.form {
		padding: 0 1.1rem 1.1rem;
		border-top: 1px solid #1e2638;
	}
	.note {
		color: #b8bfd0;
		font-size: 0.85rem;
		margin: 0.8rem 0 0.4rem;
	}
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr));
		gap: 0.3rem 0.9rem;
	}
	label {
		display: block;
		margin: 0.55rem 0 0.1rem;
		color: #8b93a7;
		font-size: 0.85rem;
	}
	label.check {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		margin-top: 1.5rem;
		color: #b8bfd0;
	}
	.req {
		color: #f0a868;
	}
	input:not([type='checkbox']),
	textarea {
		width: 100%;
		box-sizing: border-box;
		background: #0a1020;
		color: #e2e8f0;
		border: 1px solid #2a3450;
		border-radius: 6px;
		padding: 0.4rem 0.55rem;
		font: inherit;
		margin-top: 0.2rem;
	}
	.submit-row {
		margin-top: 0.9rem;
		display: flex;
		gap: 0.75rem;
		align-items: baseline;
		flex-wrap: wrap;
	}
	button.save {
		background: #155e6b;
		color: #e0fbff;
		border: 1px solid #1d7f90;
		border-radius: 6px;
		padding: 0.45rem 1rem;
		font: inherit;
		cursor: pointer;
	}
	button.save:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.ok {
		color: #6ee7b7;
		font-size: 0.85rem;
	}
	.err {
		color: #fca5a5;
		font-size: 0.85rem;
	}

	/* Layer 3 exec — the driver pulse shares the experiment heart's colour
	   identity: cyan working · blue idle · green done · red failed. */
	.exec {
		padding: 0.9rem 1.1rem 1.1rem;
		border-top: 1px solid #1e2638;
	}
	.exec-head {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		color: #dbe2f0;
		margin-bottom: 0.6rem;
	}
	.exec-head strong {
		font-size: 0.92rem;
		font-weight: 600;
	}
	.dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: #2a3450;
		flex: 0 0 auto;
	}
	.dot.working {
		background: #67e8f9;
		animation: beat 1.1s ease-out infinite;
	}
	.dot.idle {
		background: #4a7dff;
	}
	.dot.done {
		background: #6ee7b7;
	}
	.dot.failed {
		background: #fca5a5;
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
	.dstate {
		margin-left: auto;
		font-size: 0.78rem;
		color: #9aa3b8;
	}
	.dstate.working {
		color: #67e8f9;
	}
	.dstate.idle {
		color: #4a7dff;
	}
	.dstate.done {
		color: #6ee7b7;
	}
	.dstate.failed {
		color: #fca5a5;
	}
	.btn-row {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}
	button.op {
		background: #16203a;
		color: #cdd5e6;
		border: 1px solid #2a3450;
		border-radius: 6px;
		padding: 0.4rem 0.9rem;
		font: inherit;
		cursor: pointer;
	}
	button.op:hover:not(:disabled) {
		border-color: #3a4668;
	}
	button.op.go {
		background: #155e6b;
		color: #e0fbff;
		border-color: #1d7f90;
	}
	button.op.stop {
		background: #3a1622;
		color: #fca5a5;
		border-color: #6b2235;
	}
	button.op:disabled {
		opacity: 0.45;
		cursor: not-allowed;
	}
	.exec-note {
		font-size: 0.82rem;
		color: #6ee7b7;
		margin: 0.6rem 0 0.3rem;
	}
	.exec-note.bad {
		color: #fca5a5;
	}
	.exec-log {
		margin: 0.5rem 0 0;
		max-height: 16rem;
		overflow: auto;
		font-size: 0.76rem;
	}
	.exec-log code {
		background: none;
		padding: 0;
		color: #9fb4cf;
		white-space: pre-wrap;
		word-break: break-word;
	}
</style>
