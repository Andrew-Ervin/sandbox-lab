# EXAMPLE CONTRACT ONLY. Not connected to the prototype or any enterprise system.
# Every input field is assembled/verified by the trusted broker, NEVER copied from
# model arguments. In particular, approval.verified is NOT a caller-supplied flag.
package lab.mcp
import rego.v1

default allow := false

identity_ok if {
    input.identity.authenticated == true
    input.identity.tenant == input.resource.tenant
    input.identity.subject != ""
    input.resource.project in input.identity.projects
    input.catalog.tool in input.identity.tools
    input.identity.user_active == true
    input.context.origin == "managed-harness"
    input.catalog.enabled == true
    input.catalog.environment in {"development", "test", "production"}
    input.resource.classification in {"public", "internal", "confidential"}
    input.resource.classification in input.identity.data_classes
    input.request.row_limit > 0
    input.request.row_limit <= input.catalog.max_rows
    input.context.policy_version == input.catalog.policy_version
}

allow if {
    identity_ok
    input.catalog.effect == "read"
    input.catalog.read_only_transaction == true
    input.catalog.environment in input.identity.read_environments
}

approved_write if {
    identity_ok
    input.catalog.effect in {"write", "delete"}
    input.catalog.environment in input.identity.write_environments
    input.request.dry_run_complete == true
    input.request.action_hash != ""
    input.request.expected_version != ""
    input.approval.verified == true
    input.approval.subject == input.identity.subject
    input.approval.tenant == input.identity.tenant
    input.approval.project == input.resource.project
    input.approval.tool == input.catalog.tool
    input.approval.action_hash == input.request.action_hash
    input.approval.policy_version == input.context.policy_version
    input.approval.environment == input.catalog.environment
    input.approval.resource_version == input.request.expected_version
    input.approval.expires_at > input.context.now
    input.approval.consumed == false
    count(input.approval.approvers) > 0
    not input.identity.subject in input.approval.approvers
    every approver in input.approval.approvers {
        approver in input.catalog.authorized_approvers
    }
}

allow if {
    approved_write
    input.catalog.effect == "write"
    input.catalog.environment in {"development", "test"}
}

allow if {
    approved_write
    input.catalog.environment == "production"
    input.request.change_ticket_verified == true
    count({a | some a in input.approval.approvers}) >= 2
}

allow if {
    approved_write
    input.catalog.effect == "delete"
    input.catalog.environment in {"development", "test"}
    count({a | some a in input.approval.approvers}) >= 2
}
