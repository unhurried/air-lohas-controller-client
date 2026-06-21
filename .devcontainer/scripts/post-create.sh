#!/usr/bin/env bash
set -euo pipefail

workspace_dir="${1:-/workspaces/copilot-cli-devcontainer}"
template_dir="${workspace_dir}/.devcontainer"
copilot_home="${HOME}/.copilot"

install -d -m 0755 "${copilot_home}"
install -m 0644 "${template_dir}/copilot/settings.json" "${copilot_home}/settings.json"
install -m 0644 "${template_dir}/copilot/permissions-config.json" "${copilot_home}/permissions-config.json"
