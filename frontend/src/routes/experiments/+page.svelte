<script lang="ts">
	// R-D2 wires this to the local backend's signed proxy of
	// GET /api/v0/experiments (tenant-scoped). R-D0 is a placeholder.
</script>

<h1>My Experiments</h1>
<p class="muted">
	Experiment list + work-unit/replication progress land in R-D2, once the tenant SDK ships an
	RFC 9421 request signer (design note §7.1) and the local backend signs coordinator reads.
</p>

<style>
	h1 {
		font-weight: 700;
	}
	.muted {
		color: #8b93a7;
	}
</style>
