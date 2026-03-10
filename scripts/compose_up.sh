#!/usr/bin/env bash
set -euo pipefail

COMPOSE_FILE="docker/docker-compose.yml"
DEFAULT_IMAGE_REPO="quantatrisk/wps-api"
DEFAULT_IMAGE_TAG="latest"
MIN_WRITER_WORKER_COUNT=1
MAX_WRITER_WORKER_COUNT=32

image_ref="${WPS_IMAGE:-}"
image_repo="${WPS_IMAGE_REPO:-$DEFAULT_IMAGE_REPO}"
image_tag="${WPS_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
pull_policy="${WPS_IMAGE_PULL:-auto}"

usage() {
  cat <<'EOF'
Usage: ./scripts/compose_up.sh [options]

Options:
  --image <repo:tag>
  --repo <repo>
  --tag <tag>
  --pull
  --no-pull
  --help

Environment overrides:
  WPS_IMAGE
  WPS_IMAGE_REPO
  WPS_IMAGE_TAG
  WPS_IMAGE_PULL=auto|true|false
  WPS_API_PORT
  WPS_WORKER_COUNT
  WPS_BATCH_MAX_FILES
EOF
}

normalize_bool() {
  local raw_value="${1:-}"
  case "${raw_value}" in
    true|TRUE|1|yes|YES|y|Y|on|ON)
      echo "true"
      ;;
    false|FALSE|0|no|NO|n|N|off|OFF)
      echo "false"
      ;;
    auto|AUTO|"")
      echo "auto"
      ;;
    *)
      echo "Unsupported boolean value: ${raw_value}" >&2
      exit 1
      ;;
  esac
}

require_option_value() {
  local option_name="$1"
  local option_value="${2:-}"
  if [[ -z "${option_value}" ]]; then
    echo "Missing value for ${option_name}" >&2
    usage >&2
    exit 1
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)
      require_option_value "$1" "${2:-}"
      image_ref="${2:-}"
      shift 2
      ;;
    --repo)
      require_option_value "$1" "${2:-}"
      image_repo="${2:-}"
      shift 2
      ;;
    --tag)
      require_option_value "$1" "${2:-}"
      image_tag="${2:-}"
      shift 2
      ;;
    --pull)
      pull_policy="true"
      shift
      ;;
    --no-pull)
      pull_policy="false"
      shift
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

pull_policy="$(normalize_bool "${pull_policy}")"
if [[ -z "${image_ref}" ]]; then
  image_ref="${image_repo}:${image_tag}"
fi

detect_cpu_core_count() {
  if command -v lscpu >/dev/null 2>&1; then
    local lscpu_core_count
    lscpu_core_count="$(lscpu -p=core,socket 2>/dev/null | grep -v '^#' | sort -u | wc -l | tr -d ' ')"
    if [[ "${lscpu_core_count}" =~ ^[0-9]+$ ]] && [[ "${lscpu_core_count}" -gt 0 ]]; then
      echo "${lscpu_core_count}"
      return
    fi
  fi

  if [[ -r /proc/cpuinfo ]]; then
    local cpu_cores
    local socket_count
    cpu_cores="$(awk -F: '/^cpu cores[[:space:]]*:/ {gsub(/ /, "", $2); print $2; exit}' /proc/cpuinfo)"
    socket_count="$(awk -F: '/^physical id[[:space:]]*:/ {gsub(/ /, "", $2); print $2}' /proc/cpuinfo | sort -u | wc -l | tr -d ' ')"

    if [[ "${cpu_cores}" =~ ^[0-9]+$ ]] && [[ "${cpu_cores}" -gt 0 ]]; then
      if [[ "${socket_count}" =~ ^[0-9]+$ ]] && [[ "${socket_count}" -gt 0 ]]; then
        echo $((cpu_cores * socket_count))
        return
      fi
      echo "${cpu_cores}"
      return
    fi
  fi

  if command -v sysctl >/dev/null 2>&1; then
    local sysctl_core_count
    sysctl_core_count="$(sysctl -n hw.physicalcpu 2>/dev/null || true)"
    if [[ "${sysctl_core_count}" =~ ^[0-9]+$ ]] && [[ "${sysctl_core_count}" -gt 0 ]]; then
      echo "${sysctl_core_count}"
      return
    fi
  fi

  if command -v getconf >/dev/null 2>&1; then
    getconf _NPROCESSORS_ONLN
    return
  fi

  if command -v nproc >/dev/null 2>&1; then
    nproc
    return
  fi

  if command -v sysctl >/dev/null 2>&1; then
    sysctl -n hw.ncpu
    return
  fi

  echo "${MIN_WRITER_WORKER_COUNT}"
}

resolve_auto_writer_worker_count() {
  local cpu_core_count="$1"

  if [[ "${cpu_core_count}" -lt 8 ]]; then
    echo "${cpu_core_count}"
    return
  fi
  if [[ "${cpu_core_count}" -le 16 ]]; then
    echo $((cpu_core_count - 2))
    return
  fi
  echo "16"
}

clamp_writer_worker_count() {
  local value="$1"
  if [[ "${value}" -le "${MIN_WRITER_WORKER_COUNT}" ]]; then
    echo "${MIN_WRITER_WORKER_COUNT}"
    return
  fi
  if [[ "${value}" -ge "${MAX_WRITER_WORKER_COUNT}" ]]; then
    echo "${MAX_WRITER_WORKER_COUNT}"
    return
  fi
  echo "${value}"
}

resolve_writer_worker_count() {
  local raw_value="${WPS_WORKER_COUNT:-auto}"

  if [[ -z "${raw_value}" || "${raw_value}" == "auto" ]]; then
    clamp_writer_worker_count "$(resolve_auto_writer_worker_count "$(detect_cpu_core_count)")"
    return
  fi

  if ! [[ "${raw_value}" =~ ^[0-9]+$ ]]; then
    echo "WPS_WORKER_COUNT must be an integer or 'auto'" >&2
    exit 1
  fi

  clamp_writer_worker_count "${raw_value}"
}

writer_worker_count="$(resolve_writer_worker_count)"
export WPS_WORKER_COUNT="${writer_worker_count}"
export WPS_IMAGE="${image_ref}"

if [[ "${pull_policy}" == "true" ]]; then
  docker pull "${image_ref}"
elif [[ "${pull_policy}" == "auto" ]]; then
  if ! docker image inspect "${image_ref}" >/dev/null 2>&1; then
    echo "Image not found locally, pulling ${image_ref}"
    docker pull "${image_ref}"
  fi
elif ! docker image inspect "${image_ref}" >/dev/null 2>&1; then
  echo "Image not found locally: ${image_ref}" >&2
  echo "Either build it with ./scripts/build_image.sh or allow pulling from registry." >&2
  exit 1
fi

echo "Starting single-node service with ${writer_worker_count} local writer workers using ${image_ref}"
echo "This is the only supported startup entrypoint. Do not run docker compose up directly."
echo "Image pull policy: ${pull_policy}"
echo "Single service mode: one container with ${writer_worker_count} local writer workers"
exec docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans
