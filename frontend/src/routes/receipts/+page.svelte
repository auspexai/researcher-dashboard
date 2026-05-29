<script lang="ts">
	// R-D3: receipts issued to volunteers who ran *my* experiments.
	// Blocked on the coordinator's tenant-scoped receipt route
	// (GET /api/v0/experiments/{id}/receipts) — design note §7.
</script>

<h1>My Receipts</h1>
<p class="muted">
	Receipts issued to the volunteers who ran your experiments land in R-D3. This needs a new
	tenant-scoped receipt endpoint on the coordinator (design note §7) — today receipts are only
	indexed by volunteer account/worker.
</p>

<style>
	h1 {
		font-weight: 700;
	}
	.muted {
		color: #8b93a7;
	}
</style>
