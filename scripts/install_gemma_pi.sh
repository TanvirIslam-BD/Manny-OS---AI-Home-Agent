#!/usr/bin/env bash
set -euo pipefail

llama_ref="${LLAMA_CPP_REF:-b9637}"
model_dir="/opt/manny/models"
llama_dir="/opt/manny/llama.cpp"

# Variant selects the conversational model. 1b is text-only and pinned here.
# 4b is multimodal, so it also answers questions about the camera view — it needs
# a vision projector alongside the weights and a larger memory budget. On a Pi 5
# 4b generates at roughly a third of 1b's rate, so it is a vision choice, not a
# conversation one.
variant="${MANNY_GEMMA_VARIANT:-1b}"

# Quantisation. Q4_K_M is the pinned, checksum-verified default. Q4_0 is faster on
# this CPU: Cortex-A76 has dotprod, and llama.cpp repacks Q4_0 into a blocked GEMM
# kernel that Q4_K_M never uses, which mostly shortens prompt processing. Nobody
# has verified a Q4_0 checksum for this repo, so that path asks you for one.
quant="${MANNY_GEMMA_QUANT:-q4_k_m}"

case "${quant}" in
  q4_k_m) quant_tag="Q4_K_M" ;;
  q4_0) quant_tag="Q4_0" ;;
  *)
    printf 'Unknown MANNY_GEMMA_QUANT: %s (expected q4_k_m or q4_0)\n' "${quant}" >&2
    exit 2
    ;;
esac
if [[ "${variant}" != "1b" && "${variant}" != "4b" ]]; then
  printf 'Unknown MANNY_GEMMA_VARIANT: %s (expected 1b or 4b)\n' "${variant}" >&2
  exit 2
fi

model_alias="gemma-3-${variant}-it"
model_name="${model_alias}-${quant_tag}.gguf"
model_url="${MANNY_GEMMA_MODEL_URL:-}"
model_sha256="${MANNY_GEMMA_MODEL_SHA256:-}"
mmproj_name=""
mmproj_url=""
mmproj_sha256=""

# The one combination whose checksum was verified before it was pinned.
if [[ "${variant}" == "1b" && "${quant}" == "q4_k_m" && -z "${model_url}" ]]; then
  model_url="https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/${model_name}"
  model_sha256="8ccc5cd1f1b3602548715ae25a66ed73fd5dc68a210412eea643eb20eb75a135"
fi

# Everything else is unverified, and a downloaded model that nothing checks is a
# supply-chain hole, so the installer refuses rather than skipping the check.
if [[ -z "${model_url}" || -z "${model_sha256}" ]]; then
  cat >&2 <<MSG
gemma-3-${variant}-it ${quant_tag} has no checksum pinned in this repo. Supply one
you have verified yourself:

  MANNY_GEMMA_MODEL_URL     weights (${quant_tag} .gguf)
  MANNY_GEMMA_MODEL_SHA256  sha256sum of the weights

Download it once, run sha256sum yourself, then re-run with those values set.
The pinned combination that needs no arguments is:
  MANNY_GEMMA_VARIANT=1b MANNY_GEMMA_QUANT=q4_k_m
MSG
  exit 2
fi

if [[ "${variant}" == "4b" ]]; then
  mmproj_name="gemma-3-4b-it-mmproj-F16.gguf"
  mmproj_url="${MANNY_GEMMA_4B_MMPROJ_URL:-}"
  mmproj_sha256="${MANNY_GEMMA_4B_MMPROJ_SHA256:-}"
  if [[ -z "${mmproj_url}" || -z "${mmproj_sha256}" ]]; then
    cat >&2 <<'MSG'
The 4B multimodal variant also needs its vision projector, checksum included:

  MANNY_GEMMA_4B_MMPROJ_URL     vision projector (.gguf)
  MANNY_GEMMA_4B_MMPROJ_SHA256  sha256sum of the projector
MSG
    exit 2
  fi
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

# manny-llm.service reads this instead of hardcoding a filename. The unit and the
# installed weights used to be edited separately, so a default install downloaded
# 1B while the unit launched 4B and llama-server exited on a missing file.
cat >/opt/manny/model.env <<EOF
MANNY_LLM_MODEL_FILE=${model_dir}/${model_name}
MANNY_LLM_MODEL_ALIAS=${model_alias}
EOF
chown root:manny /opt/manny/model.env
chmod 0640 /opt/manny/model.env

cat <<EOF
Gemma installed: ${model_name}
Recorded in /opt/manny/model.env, which manny-llm.service reads at start.

Set MANNY_LLM_MODEL=${model_alias} in /opt/manny/.env so the core sends the same
name the server answers to.

Run install_systemd.sh, then explicitly enable manny-llm and manny-core.
EOF
