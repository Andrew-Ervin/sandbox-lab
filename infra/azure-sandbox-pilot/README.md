# Azure Sandbox pilot templates

These templates describe consumption-only Sandbox groups, private Blob storage, the approved Basic registry, and the separate custom Dynamic Sessions experiment. The app uses the three Sandbox groups. The custom session pool and its dedicated-profile environment have been removed after the bounded test.

Never deploy the whole directory implicitly. Review a specific template and its price first. Fixed-cost resource creation requires user permission. The registry approval covers Basic for the testing period; the previous two-hour Session Pool approval has expired and is not standing permission to recreate it.

See [current runtime](../../docs/AZURE-SANDBOX-RUNTIME.md), [scaling and pricing](../../docs/SCALING.md), and [setup](../../docs/LOCAL-SETUP.md). Private configuration, credentials, cloud IDs, execution receipts and billing evidence stay in ignored local state.

## Built-in Python runtime routing

Deploy `builtin-sessions.json`, assign the broker identity the scoped Session Executor role, then set these values in the ignored `.local/azure-runtime/config.json` (substitute your resource endpoint):

```json
{
  "builtin_session_endpoint": "https://REGION.dynamicsessions.io/subscriptions/SUBSCRIPTION/resourceGroups/GROUP/sessionPools/POOL",
  "builtin_session_limit": 10
}
```

Restart the broker after configuring. The pool template holds sessions for 55 idle minutes with blocked egress. Match the broker limit to the deployed pool. The broker records conservative hourly estimates, not actual invoiced spend; the $200 pilot admission guard remains separate from billing observations.
