#!/usr/bin/env bash
set -euo pipefail

whisper_ref="${WHISPER_CPP_REF:-v1.9.2}"
whisper_dir="/opt/manny/whisper.cpp"
model_dir="/opt/manny/models"
model_name="ggml-base.bin"
model_url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${model_name}"
model_sha256="60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"

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
This installs multilingual whisper.cpp speech recognition and eSpeak NG speech output.
The local Whisper base model is about 148 MB and automatically detects spoken language.
eSpeak NG provides broad offline coverage; voice quality varies by language.
EOF
read -r -p 'Install the multilingual local voice runtime? [y/N] ' answer
[[ "${answer}" == y || "${answer}" == Y ]] || exit 0

apt-get update
apt-get install -y --no-install-recommends build-essential ca-certificates cmake curl \
  espeak-ng git libespeak-ng1

if [[ ! -d "${whisper_dir}/.git" ]]; then
  git clone https://github.com/ggml-org/whisper.cpp.git "${whisper_dir}"
fi
git -C "${whisper_dir}" fetch --tags --prune
git -C "${whisper_dir}" checkout --detach "${whisper_ref}"
cmake -S "${whisper_dir}" -B "${whisper_dir}/build" -DCMAKE_BUILD_TYPE=Release \
  -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON
cmake --build "${whisper_dir}/build" --config Release -j 4 --target whisper-cli

install -d -o root -g manny -m 0750 "${model_dir}"
curl --fail --location --retry 3 --output "${model_dir}/${model_name}.download" "${model_url}"
echo "${model_sha256}  ${model_dir}/${model_name}.download" | sha256sum --check -
mv "${model_dir}/${model_name}.download" "${model_dir}/${model_name}"
chown root:manny "${model_dir}/${model_name}"
chmod 0640 "${model_dir}/${model_name}"
chmod 0755 "${whisper_dir}/build/bin/whisper-cli"

echo 'Multilingual voice installed. Run verify_hardware.sh before enabling Manny services.'
