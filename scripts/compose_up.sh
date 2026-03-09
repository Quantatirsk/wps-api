#!/usr/bin/env bash
set -euo pipefail

compose_file="docker/docker-compose.yml"
image_name="${WPS_IMAGE:-quantatrisk/wps-api:latest}"
min_writer_worker_count=1
max_writer_worker_count=32

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

  echo "${min_writer_worker_count}"
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
  if [[ "${value}" -le "${min_writer_worker_count}" ]]; then
    echo "${min_writer_worker_count}"
    return
  fi
  if [[ "${value}" -ge "${max_writer_worker_count}" ]]; then
    echo "${max_writer_worker_count}"
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

if ! docker image inspect "${image_name}" >/dev/null 2>&1; then
  echo "Image not found: ${image_name}" >&2
  echo "Build it first with ./scripts/build_image.sh" >&2
  exit 1
fi

echo "Starting single-node service with ${writer_worker_count} local writer workers using ${image_name}"
echo "This is the only supported startup entrypoint. Do not run docker compose up directly."
echo "Single service mode: one container with ${writer_worker_count} local writer workers"
exec docker compose -f "${compose_file}" up -d --remove-orphans
