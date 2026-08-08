#!/usr/bin/env bash
set -euo pipefail

llama_ref="${LLAMA_CPP_REF:-b9637}"
model_dir="/opt/manny/models"
llama_dir="/opt/manny/llama.cpp"
model_name="gemma-3-1b-it-Q4_K_M.gguf"
model_url="https://huggingface.co/ggml-org/gemma-3-1b-it-GGUF/resolve/main/${model_name}"
model_sha256="8ccc5cd1f1b3602548715ae25a66ed73fd5dc68a210412eea643eb20eb75a135"

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
This installs llama.cpp and the Gemma 3 1B IT Q4_K_M model locally.
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
curl --fail --location --retry 3 --output "${model_dir}/${model_name}.download" "${model_url}"
echo "${model_sha256}  ${model_dir}/${model_name}.download" | sha256sum --check -
mv "${model_dir}/${model_name}.download" "${model_dir}/${model_name}"
chown root:manny "${model_dir}/${model_name}"
chmod 0640 "${model_dir}/${model_name}"
chmod 0755 "${llama_dir}/build/bin/llama-server"

echo 'Gemma installed. Run install_systemd.sh, then explicitly enable manny-llm and manny-core.'
