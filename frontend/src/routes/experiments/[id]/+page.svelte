<script lang="ts">
	import { page } from '$app/state';
	const id = $derived(page.params.id);
	// R-D2: detail + work-units (GET /experiments/{id}, /experiments/{id}/work-units).
	// R-D4: lifecycle actions (abort, pause/resume), confirm-gated.
</script>

<h1>Experiment {id}</h1>
<p class="muted">
	Detail, work-unit progress, and the abort action land in R-D2/R-D4.
</p>

<style>
	h1 {
		font-weight: 700;
	}
	.muted {
		color: #8b93a7;
	}
</style>
