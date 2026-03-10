#!/usr/bin/env bash
set -euo pipefail

DEFAULT_IMAGE_NAME="quantatrisk/wps-api"
DEFAULT_IMAGE_TAG="latest"
DEFAULT_DOCKERFILE_PATH="docker/Dockerfile"

image_name="${WPS_IMAGE_NAME:-$DEFAULT_IMAGE_NAME}"
image_tag="${WPS_IMAGE_TAG:-$DEFAULT_IMAGE_TAG}"
target_platform="${WPS_BUILD_PLATFORM:-host}"
no_cache="${WPS_BUILD_NO_CACHE:-false}"
assume_yes="${WPS_BUILD_YES:-false}"
push_image="${WPS_BUILD_PUSH:-}"
buildx_builder_name="${WPS_BUILDX_BUILDER_NAME:-wps-api-builder}"

usage() {
  cat <<'EOF'
Usage: ./scripts/build_image.sh [options]

Options:
  --platform <host|amd64|arm64|all|linux/amd64|linux/arm64>
  --image-name <name>
  --image-tag <tag>
  --no-cache
  --push
  --yes
  --help

Environment overrides:
  WPS_BUILD_PLATFORM
  WPS_IMAGE_NAME
  WPS_IMAGE_TAG
  WPS_BUILD_NO_CACHE=true
  WPS_BUILD_YES=true
  WPS_BUILD_PUSH=true
  WPS_BUILDX_BUILDER_NAME
  WPS_DEB_URL_BASE
  PYWPSRPC_WHEEL_URL
  FONTS_ZIP_URL
EOF
}

detect_host_platform() {
  case "$(uname -m)" in
    arm64|aarch64)
      echo "linux/arm64"
      ;;
    x86_64|amd64)
      echo "linux/amd64"
      ;;
    *)
      echo "Unsupported host architecture: $(uname -m)" >&2
      exit 1
      ;;
  esac
}

normalize_platform() {
  local raw_value="${1:-host}"
  case "${raw_value}" in
    host|auto|"")
      detect_host_platform
      ;;
    all|multi|multi-arch|linux/amd64,linux/arm64)
      echo "linux/amd64,linux/arm64"
      ;;
    arm64|aarch64|linux/arm64)
      echo "linux/arm64"
      ;;
    amd64|x86_64|linux/amd64)
      echo "linux/amd64"
      ;;
    *)
      echo "Unsupported platform: ${raw_value}" >&2
      exit 1
      ;;
  esac
}

resource_summary() {
  case "$1" in
    linux/amd64,linux/arm64)
      echo "Multi-arch manifest: amd64 + arm64"
      ;;
    linux/arm64)
      echo "WPS arm64 package + ARM pywpsrpc wheel"
      ;;
    linux/amd64)
      echo "WPS amd64 package + PyPI pywpsrpc"
      ;;
    *)
      echo "custom"
      ;;
  esac
}

append_build_arg_if_set() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "${value}" ]]; then
    build_cmd+=(--build-arg "${name}=${value}")
  fi
}

ensure_buildx_builder() {
  if docker buildx inspect "${buildx_builder_name}" >/dev/null 2>&1; then
    docker buildx use "${buildx_builder_name}" >/dev/null
  else
    docker buildx create --name "${buildx_builder_name}" --driver docker-container --use >/dev/null
  fi
  docker buildx inspect "${buildx_builder_name}" --bootstrap >/dev/null
}

normalize_bool() {
  local raw_value="${1:-}"
  case "${raw_value}" in
    true|TRUE|1|yes|YES|y|Y|on|ON)
      echo "true"
      ;;
    false|FALSE|0|no|NO|n|N|off|OFF|"")
      echo "false"
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
    --platform)
      require_option_value "$1" "${2:-}"
      target_platform="${2:-}"
      shift 2
      ;;
    --image-name)
      require_option_value "$1" "${2:-}"
      image_name="${2:-}"
      shift 2
      ;;
    --image-tag)
      require_option_value "$1" "${2:-}"
      image_tag="${2:-}"
      shift 2
      ;;
    --no-cache)
      no_cache="true"
      shift
      ;;
    --push)
      push_image="true"
      shift
      ;;
    --yes)
      assume_yes="true"
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

target_platform="$(normalize_platform "${target_platform}")"
no_cache="$(normalize_bool "${no_cache}")"
assume_yes="$(normalize_bool "${assume_yes}")"
primary_ref="${image_name}:${image_tag}"
extra_tags=()
push_refs=("${primary_ref}")
is_multi_platform="false"
build_mode="docker"

if [[ "${target_platform}" == *","* ]]; then
  is_multi_platform="true"
  build_mode="buildx"
fi

if [[ "${target_platform}" == "linux/arm64" && "${image_tag}" != "latest" ]]; then
  extra_tags+=("latest")
  push_refs+=("${image_name}:latest")
fi

if [[ "${is_multi_platform}" == "true" && "${image_tag}" != "latest" ]]; then
  extra_tags=("latest")
  push_refs=("${primary_ref}" "${image_name}:latest")
fi

if [[ "${is_multi_platform}" == "true" ]]; then
  if [[ -z "${push_image}" ]]; then
    push_image="true"
  fi
  if [[ "$(normalize_bool "${push_image}")" != "true" ]]; then
    echo "Multi-arch build requires pushing to a registry. Use --push or set WPS_BUILD_PUSH=true." >&2
    exit 1
  fi
fi

if [[ "${build_mode}" == "buildx" ]]; then
  build_cmd=(docker buildx build --builder "${buildx_builder_name}" -f "${DEFAULT_DOCKERFILE_PATH}" --platform "${target_platform}" -t "${primary_ref}")
else
  build_cmd=(docker build -f "${DEFAULT_DOCKERFILE_PATH}" --platform "${target_platform}" -t "${primary_ref}")
fi

if [[ "${no_cache}" == "true" ]]; then
  build_cmd+=(--no-cache)
fi

append_build_arg_if_set "WPS_DEB_URL_BASE"
append_build_arg_if_set "PYWPSRPC_WHEEL_URL"
append_build_arg_if_set "FONTS_ZIP_URL"

if [[ "${build_mode}" == "buildx" ]]; then
  for extra_tag in "${extra_tags[@]}"; do
    build_cmd+=(-t "${image_name}:${extra_tag}")
  done
  build_cmd+=(--push)
fi

build_cmd+=(.)

if [[ -z "${push_image}" ]]; then
  push_image="false"
else
  push_image="$(normalize_bool "${push_image}")"
fi

echo "Target platform: ${target_platform}"
echo "Build mode: ${build_mode}"
echo "Resource profile: $(resource_summary "${target_platform}")"
if [[ -n "${WPS_DEB_URL_BASE:-}" ]]; then
  echo "Override: WPS_DEB_URL_BASE"
fi
if [[ -n "${PYWPSRPC_WHEEL_URL:-}" ]]; then
  echo "Override: PYWPSRPC_WHEEL_URL"
fi
if [[ -n "${FONTS_ZIP_URL:-}" ]]; then
  echo "Override: FONTS_ZIP_URL"
fi
if ((${#extra_tags[@]} > 0)); then
  echo "Extra tags: ${extra_tags[*]}"
fi
echo
echo "将执行以下命令:"
printf '  %q' "${build_cmd[@]}"
echo

if [[ "${is_multi_platform}" != "true" && "${WPS_BUILD_PUSH:-}" == "" && "${assume_yes}" != "true" ]]; then
  read -r -p "构建完成后是否推送到 Docker Hub? [y/N]: " push_answer
  push_image="$(normalize_bool "${push_answer}")"
fi

if [[ "${push_image}" == "true" ]]; then
  echo "Push targets:"
  for ref in "${push_refs[@]}"; do
    echo "  ${ref}"
  done
  echo
fi

if [[ "${assume_yes}" != "true" ]]; then
  read -r -p "确认开始构建? [Y/n]: " confirm_answer
  confirm_answer="${confirm_answer:-Y}"
  case "${confirm_answer}" in
    n|N|no|NO)
      echo "已取消。"
      exit 0
      ;;
  esac
fi

if [[ "${build_mode}" == "buildx" ]]; then
  ensure_buildx_builder
fi

"${build_cmd[@]}"

if [[ "${build_mode}" == "docker" ]]; then
  for extra_tag in "${extra_tags[@]}"; do
    docker tag "${primary_ref}" "${image_name}:${extra_tag}"
  done

  if [[ "${push_image}" == "true" ]]; then
    for ref in "${push_refs[@]}"; do
      docker push "${ref}"
    done
  fi
fi
