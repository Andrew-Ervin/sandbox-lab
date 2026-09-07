package lab.mcp_test
import rego.v1
import data.lab.mcp

base := {
    "identity": {"authenticated":true,"tenant":"example-tenant","subject":"employee",
        "projects":["demo"],"tools":["inventory.adjust"],"user_active":true,
        "data_classes":["internal"],"read_environments":["development","production"],
        "write_environments":["development","production"]},
    "resource":{"tenant":"example-tenant","project":"demo","classification":"internal"},
    "catalog":{"tool":"inventory.adjust","enabled":true,"environment":"development",
        "effect":"write","max_rows":20,"policy_version":"v1","read_only_transaction":true,
        "authorized_approvers":["reviewer-a","reviewer-b"]},
    "context":{"origin":"managed-harness","policy_version":"v1","now":100},
    "request":{"row_limit":1,"dry_run_complete":true,"action_hash":"fixture-action-hash",
        "expected_version":"fixture-etag","change_ticket_verified":true},
    "approval":{"verified":true,"subject":"employee","tenant":"example-tenant","project":"demo",
        "tool":"inventory.adjust","action_hash":"fixture-action-hash","policy_version":"v1",
        "environment":"development","resource_version":"fixture-etag","expires_at":200,
        "consumed":false,"approvers":["reviewer-a"]}
}

test_empty_denied if { not mcp.allow with input as {} }
test_approved_dev_write if { mcp.allow with input as base }
test_read_without_approval if {
    mcp.allow with input as base with input.catalog.effect as "read" with input.approval as {}
}
test_external_script_denied if { not mcp.allow with input as base with input.context.origin as "workspace-code" }
test_wrong_tenant_denied if { not mcp.allow with input as base with input.identity.tenant as "other" }
test_wrong_project_denied if { not mcp.allow with input as base with input.resource.project as "other" }
test_disabled_user_denied if { not mcp.allow with input as base with input.identity.user_active as false }
test_direct_sql_not_in_catalog if { not mcp.allow with input as base with input.catalog.tool as "sql.execute" }
test_large_write_denied if { not mcp.allow with input as base with input.request.row_limit as 21 }
test_unverified_approval_denied if { not mcp.allow with input as base with input.approval.verified as false }
test_changed_action_denied if { not mcp.allow with input as base with input.request.action_hash as "different" }
test_stale_resource_denied if { not mcp.allow with input as base with input.request.expected_version as "new-etag" }
test_expired_approval_denied if { not mcp.allow with input as base with input.context.now as 200 }
test_replay_denied if { not mcp.allow with input as base with input.approval.consumed as true }
test_self_approval_denied if { not mcp.allow with input as base with input.approval.approvers as ["employee"] }
test_unauthorized_reviewer_denied if { not mcp.allow with input as base with input.approval.approvers as ["outsider"] }
test_changed_policy_denied if { not mcp.allow with input as base with input.context.policy_version as "v2" }
test_prod_needs_two_reviewers if {
    not mcp.allow with input as base with input.catalog.environment as "production" with input.approval.environment as "production"
}
test_prod_approved if {
    mcp.allow with input as base with input.catalog.environment as "production" with input.approval.environment as "production"
        with input.approval.approvers as ["reviewer-a","reviewer-b"]
}
test_duplicate_approvers_denied if {
    not mcp.allow with input as base with input.catalog.environment as "production" with input.approval.environment as "production"
        with input.approval.approvers as ["reviewer-a","reviewer-a"]
}
test_delete_needs_two_reviewers if { not mcp.allow with input as base with input.catalog.effect as "delete" }
