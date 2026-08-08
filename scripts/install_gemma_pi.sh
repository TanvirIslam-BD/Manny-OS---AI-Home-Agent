#!/usr/bin/env bash
set -euo pipefail

llama_ref="${LLAMA_CPP_REF:-b9637}"
model_dir="/opt/manny/models"
llama_dir="/opt/manny/llama.cpp"

# Variant selects the conversational model. 1b is text-only and pinned here.
# 4b is multimodal, so it also answers questions about the camera view — it needs
# a vision projector alongside the weights and a larger memory budget.
variant="${MANNY_GEMMA_VARIANT:-1b}"

model_name="gemma-3-1b-it-Q4_K_M.gguf"
model_url="https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/${model_name}"
model_sha256="8ccc5cd1f1b3602548715ae25a66ed73fd5dc68a210412eea643eb20eb75a135"
mmproj_name=""
mmproj_url=""
mmproj_sha256=""

if [[ "${variant}" == "4b" ]]; then
  model_name="gemma-3-4b-it-Q4_K_M.gguf"
  model_url="${MANNY_GEMMA_4B_URL:-}"
  model_sha256="${MANNY_GEMMA_4B_SHA256:-}"
  mmproj_name="gemma-3-4b-it-mmproj-F16.gguf"
  mmproj_url="${MANNY_GEMMA_4B_MMPROJ_URL:-}"
  mmproj_sha256="${MANNY_GEMMA_4B_MMPROJ_SHA256:-}"
  # The 1B checksum above was verified before it was pinned. These have not
  # been, and a downloaded model that nothing verifies is a supply-chain hole,
  # so the installer refuses rather than skipping the check.
  if [[ -z "${model_url}" || -z "${model_sha256}" || -z "${mmproj_url}" || -z "${mmproj_sha256}" ]]; then
    cat >&2 <<'MSG'
The 4B multimodal variant needs URLs and SHA-256 checksums you have verified:

  MANNY_GEMMA_4B_URL            weights (Q4_K_M .gguf)
  MANNY_GEMMA_4B_SHA256         sha256sum of the weights
  MANNY_GEMMA_4B_MMPROJ_URL     vision projector (.gguf)
  MANNY_GEMMA_4B_MMPROJ_SHA256  sha256sum of the projector

Download each once, run sha256sum yourself, then re-run with those values set.
MSG
    exit 2
  fi
elif [[ "${variant}" != "1b" ]]; then
  printf 'Unknown MANNY_GEMMA_VARIANT: %s (expected 1b or 4b)
' "${variant}" >&2
  exit 2
fi

if [[ "$(uname -m)" != aarch64 ]] || ! grep -qi raspberry /proc/device-tree/model; then
  echo 'This installer only runs on an ARM64 Raspberry Pi.' >&2
  exit 1
fi
if [[ "${EUID}" -ne 0 ]]; then
  echo 'Run with sudo after reviewing this script.' >&2
  exit 1
fi
if ! id manny >/dev/null 2>&1; then
  echo 'Run bootstrap_pi.sh first to create the manny service user.' >&2
  exit 1
fi

cat <<'EOF'
This installs llama.cpp and a Gemma 3 IT Q4_K_M model locally.
Gemma is distributed under Google's Gemma license and prohibited-use policy.
Review and accept those terms before continuing:
https://ai.google.dev/gemma/terms
EOF
read -r -p 'Download and install the local model? [y/N] ' answer
[[ "${answer}" == y || "${answer}" == Y ]] || exit 0

apt-get update
apt-get install -y --no-install-recommends build-essential ca-certificates cmake curl git libcurl4-openssl-dev

if [[ ! -d "${llama_dir}/.git" ]]; then
  git clone https://github.com/ggml-org/llama.cpp.git "${llama_dir}"
fi
git -C "${llama_dir}" fetch --tags --prune
git -C "${llama_dir}" checkout --detach "${llama_ref}"
cmake -S "${llama_dir}" -B "${llama_dir}/build" -DCMAKE_BUILD_TYPE=Release \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_SERVER=ON
cmake --build "${llama_dir}/build" --config Release -j 4 --target llama-server

install -d -o root -g manny -m 0750 "${model_dir}"
fetch_verified() {
  local name="$1" url="$2" digest="$3"
  curl --fail --location --retry 3 --output "${model_dir}/${name}.download" "${url}"
  echo "${digest}  ${model_dir}/${name}.download" | sha256sum --check -
  mv "${model_dir}/${name}.download" "${model_dir}/${name}"
  chown root:manny "${model_dir}/${name}"
  chmod 0640 "${model_dir}/${name}"
}

fetch_verified "${model_name}" "${model_url}" "${model_sha256}"
if [[ -n "${mmproj_name}" ]]; then
  fetch_verified "${mmproj_name}" "${mmproj_url}" "${mmproj_sha256}"
fi
chmod 0755 "${llama_dir}/build/bin/llama-server"

echo 'Gemma installed. Run install_systemd.sh, then explicitly enable manny-llm and manny-core.'
