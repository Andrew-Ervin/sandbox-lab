# Runtime limits

Public file, output, package and model controls live in `config/limits.env`. Private Azure profiles live in `.local/azure-runtime/config.json`. The documentation API returns a curated subset of actual configured values, never secrets.

Source sync permits 2,000 files, 8 MB per file, 32 MB total and 10,000 scanned directory entries. Quick checkpoints/artifacts allow 40 files, 8 MB each and 16 MB total. Quick execution has a 30-second wall limit, 25 CPU seconds and bounded output. Preview listeners expire after two minutes without renewal. Read-only sync uses two concurrent transfers and a 15-second interval.

The job scheduler has 128 active slots and no pending-count cap. A project's writes are serialized. Runtime resource admission is independently guarded by cloud quotas, per-role active ceilings and a $12/hour aggregate compute allowance. The cumulative pilot budget can reject further reservations before those resource ceilings are reached. See [scaling](SCALING.md).

Do not weaken resource, network, package-age or approval controls to make a test pass. Change and reprice profiles deliberately; validate boundary behavior after changing these limits.
