terraform {
  required_providers {
    coder = { source = "coder/coder", version = "2.18.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "2.38.0" }
  }
}
provider "coder" {}
provider "kubernetes" {}
data "coder_workspace" "me" {}
data "coder_workspace_owner" "me" {}
variable "namespace" { type = string }
variable "image" { type = string }
variable "gui" { type = bool }
variable "coder_url" { type = string }
variable "model" {
  type = string
  default = "openai/gpt-5.6-luna"
}
variable "reasoning" {
  type = string
  default = "xhigh"
}
variable "architecture" {
  type = string
  validation {
    condition = contains(["amd64", "arm64"], var.architecture)
    error_message = "architecture must match the Kubernetes nodes and image: amd64 or arm64."
  }
}
variable "runtime_class_name" {
  type = string
  default = ""
}
variable "image_pull_policy" {
  type = string
  default = "Never"
}
variable "memory_request" {
  type = string
  default = "512Mi"
}
variable "cpu_request" {
  type = string
  default = "500m"
}
variable "storage_class_name" {
  type = string
  default = ""
}
variable "memory_limit" {
  type = string
  default = "4Gi"
}
resource "coder_agent" "main" {
  arch = var.architecture
  os = "linux"
  dir = "/home/sandbox/project"
  startup_script = <<-EOT
    set -eu
    mkdir -p /home/sandbox/project/artifacts
    sh /opt/lab/project-init.sh
    python /opt/lab/harness_setup.py <<'CONFIG'
    ${jsonencode({ model = var.model, reasoning = var.reasoning, gui = var.gui })}
    CONFIG
    if [ "${var.gui}" = "true" ]; then
      code-server --auth none --bind-addr 127.0.0.1:13337 /home/sandbox/project > /tmp/code-server.log 2>&1 &
    fi
  EOT
  env = {
    HTTP_PROXY = "http://package-proxy.lab-control.svc.cluster.local:3128"
    HTTPS_PROXY = "http://package-proxy.lab-control.svc.cluster.local:3128"
    http_proxy = "http://package-proxy.lab-control.svc.cluster.local:3128"
    https_proxy = "http://package-proxy.lab-control.svc.cluster.local:3128"
    NO_PROXY = "localhost,127.0.0.1,.svc,.cluster.local"
    PI_TELEMETRY = "0"
    ORI_TELEMETRY = "0"
    ORI_NO_UPDATE_CHECK = "1"
    JULIA_NUM_PRECOMPILE_TASKS = "1"
    JULIA_PKG_SERVER = "http://package-proxy.lab-control.svc.cluster.local:3128/julia"
    UV_INDEX_URL = "http://package-proxy.lab-control.svc.cluster.local:3128/python/simple/"
    UV_INSECURE_HOST = "package-proxy.lab-control.svc.cluster.local"
  }
}
resource "coder_app" "vscode" {
  count = var.gui ? 1 : 0
  agent_id = coder_agent.main.id
  slug = "vscode"
  display_name = "VS Code"
  icon = "/icon/code.svg"
  url = "http://localhost:13337/?folder=/home/sandbox/project"
  subdomain = false
  share = "owner"
  healthcheck {
    url = "http://localhost:13337/healthz"
    interval = 5
    threshold = 6
  }
}
resource "coder_app" "preview" {
  agent_id = coder_agent.main.id
  slug = "preview"
  display_name = "App preview"
  icon = "/icon/widgets.svg"
  url = "http://localhost:3000"
  subdomain = false
  share = "owner"
}
resource "kubernetes_persistent_volume_claim_v1" "home" {
  wait_until_bound = false
  metadata {
    name = "home-${data.coder_workspace.me.id}"
    namespace = var.namespace
  }
  spec {
    access_modes = ["ReadWriteOnce"]
    storage_class_name = var.storage_class_name == "" ? null : var.storage_class_name
    resources { requests = { storage = "2Gi" } }
  }
}
resource "kubernetes_pod_v1" "workspace" {
  count = data.coder_workspace.me.start_count
  metadata {
    name = "ws-${data.coder_workspace.me.id}"
    namespace = var.namespace
    labels = { "lab/managed" = "true", "lab/mode" = var.gui ? "developer" : "coder-agent", "lab/workspace" = data.coder_workspace.me.id }
  }
  spec {
    runtime_class_name = var.runtime_class_name == "" ? null : var.runtime_class_name
    dns_policy = "None"
    dns_config {
      nameservers = ["10.96.0.53"]
      searches = ["${var.namespace}.svc.cluster.local", "svc.cluster.local", "cluster.local"]
      option {
        name = "ndots"
        value = "1"
      }
    }
    service_account_name = "unprivileged"
    automount_service_account_token = false
    termination_grace_period_seconds = 10
    security_context {
      run_as_non_root = true
      run_as_user = 1000
      run_as_group = 1000
      fs_group = 1000
      seccomp_profile { type = "RuntimeDefault" }
    }
    container {
      name = "workspace"
      image = var.image
      image_pull_policy = var.image_pull_policy
      command = ["sh", "-c", coder_agent.main.init_script]
      env {
        name = "CODER_AGENT_TOKEN"
        value = coder_agent.main.token
      }
      env {
        name = "CODER_AGENT_URL"
        value = var.coder_url
      }
      security_context {
        run_as_non_root = true
        run_as_user = 1000
        run_as_group = 1000
        allow_privilege_escalation = false
        read_only_root_filesystem = true
        capabilities { drop = ["ALL"] }
      }
      resources {
        requests = { cpu = var.cpu_request, memory = var.memory_request }
        limits = { cpu = "2", memory = var.memory_limit, "ephemeral-storage" = var.gui ? "2Gi" : "512Mi" }
      }
      volume_mount {
        name = "home"
        mount_path = "/home/sandbox"
      }
      volume_mount {
        name = "tmp"
        mount_path = "/tmp"
      }
      volume_mount {
        name = "work"
        mount_path = "/workspace"
      }
    }
    volume {
      name = "home"
      persistent_volume_claim { claim_name = kubernetes_persistent_volume_claim_v1.home.metadata[0].name }
    }
    volume {
      name = "tmp"
      empty_dir { size_limit = var.gui ? "1Gi" : "256Mi" }
    }
    volume {
      name = "work"
      empty_dir { size_limit = "256Mi" }
    }
  }
}
