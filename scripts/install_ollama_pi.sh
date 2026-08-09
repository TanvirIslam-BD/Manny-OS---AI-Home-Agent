#!/usr/bin/env bash
# Install the Ollama runtime and pull Manny's conversational model.
#
# Replaces install_gemma_pi.sh, which built llama.cpp from source and downloaded a
# checksum-pinned GGUF (ADR-020).
#
# One deliberate asymmetry in what is verified here. The Ollama *binary* is
# checksum-verified, because it runs as a service and an unverified download would
# be arbitrary code execution as root. Model *pulls* are not verified, because
# Ollama's registry offers no equivalent to a pinned SHA — that guarantee is what
# adopting Ollama gives up, and it is recorded as a consequence rather than hidden.
set -euo pipefail

model="${MANNY_OLLAMA_MODEL:-gemma4:e2b}"
install_root=/opt/manny
drop_in_dir=/etc/systemd/system/ollama.service.d

url="${MANNY_OLLAMA_URL:-}"
digest="${MANNY_OLLAMA_SHA256:-}"

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

if [[ -z "${url}" || -z "${digest}" ]]; then
  cat >&2 <<'MSG'
The Ollama runtime needs a URL and SHA-256 you have verified yourself:

  MANNY_OLLAMA_URL     ollama-linux-arm64.tgz release asset
  MANNY_OLLAMA_SHA256  sha256sum of that archive

Take both from the release you intend to run, check the sum locally, then re-run
with those values set. This is a service binary, so it is verified even though the
model pulled below cannot be.

Piping an install script from the network into root is what this avoids.
MSG
  exit 2
fi

cat <<EOF
This installs the Ollama runtime and pulls ${model}.
The model is distributed under its publisher's licence and prohibited-use policy.
Review and accept those terms before continuing.
EOF
read -r -p "Install Ollama and pull ${model}? [y/N] " answer
[[ "${answer}" == y || "${answer}" == Y ]] || exit 0

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl

workspace="$(mktemp -d)"
trap 'rm -rf "${workspace}"' EXIT
archive="${workspace}/ollama.tgz"
curl --fail --location --retry 3 --output "${archive}" "${url}"
echo "${digest}  ${archive}" | sha256sum --check -
tar -C /usr -xzf "${archive}"
command -v ollama >/dev/null 2>&1 || {
  echo 'The archive did not provide an ollama binary on PATH.' >&2
  exit 1
}

if ! id ollama >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /usr/share/ollama --shell /bin/false ollama
fi
install -d -m 0755 "${drop_in_dir}"
# Ollama ships its own unit, so Manny constrains it with a drop-in rather than
# replacing it. OLLAMA_HOST is pinned because the repository invariant is that local
# inference never listens off-loopback, and that variable is the only thing deciding
# it. One loaded model at a time keeps an 8 GB board from being asked to hold two.
cat >"${drop_in_dir}/manny.conf" <<'EOF'
[Service]
Environment=OLLAMA_HOST=127.0.0.1:11434
Environment=OLLAMA_MAX_LOADED_MODELS=1
# Every parallel slot gets its own KV cache, so more than one multiplies the memory
# a half-duplex device can never use: only one turn runs at a time.
Environment=OLLAMA_NUM_PARALLEL=1
# Bound the KV cache rather than accepting a default sized for a larger machine.
# Manny's prompt measures about 1,950 tokens at full stretch: a ~940-token system
# instruction, four turns of history, four recalled notes, the question, and a
# 320-token reply. 3,072 leaves real headroom; 2,048 does not, and an overflow is not
# a soft failure — truncation would drop the instruction carrying the finance rules.
Environment=OLLAMA_CONTEXT_LENGTH=3072
# Flash attention is what allows the KV cache to be quantised; q8_0 roughly halves
# it for no quality change worth measuring at this size.
Environment=OLLAMA_FLASH_ATTENTION=1
Environment=OLLAMA_KV_CACHE_TYPE=q8_0
# Keep the model resident between turns. Reloading several gigabytes mid-conversation
# is a multi-second stall on this hardware, which is the failure that made a pinned
# llama-server predictable and a model manager not.
Environment=OLLAMA_KEEP_ALIVE=-1
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
# No MemoryMax on purpose. E2B's resident size depends on whether the runtime
# offloads per-layer embeddings, so a ceiling guessed here would either be useless or
# would OOM-kill the model weeks later. Measure with `ollama ps` on this device, then
# set one deliberately.
EOF

if [[ ! -f /etc/systemd/system/ollama.service ]] && [[ ! -f /lib/systemd/system/ollama.service ]]; then
  cat >/etc/systemd/system/ollama.service <<'EOF'
[Unit]
Description=Ollama local model runtime
After=network-online.target

[Service]
Type=simple
User=ollama
Group=ollama
ExecStart=/usr/bin/ollama serve

[Install]
WantedBy=multi-user.target
EOF
  echo 'The archive shipped no unit, so a minimal one was installed.'
fi

systemctl daemon-reload
systemctl enable --now ollama

# The daemon has to answer before a pull can succeed.
for _ in $(seq 1 30); do
  curl -sf --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
  sleep 1
done

if ! ollama pull "${model}"; then
  cat >&2 <<MSG

Pulling ${model} failed. The usual cause is that the tag does not exist.
Check the name with:

  ollama show ${model}

then re-run with MANNY_OLLAMA_MODEL set to a tag the registry publishes.
MSG
  exit 1
fi

resident="$(ollama ps 2>/dev/null | tail -n +2 || true)"
cat <<EOF

Ollama installed and ${model} pulled.

Set MANNY_LLM_MODEL=${model} in ${install_root}/.env so the core requests the tag
that is actually present.

Two numbers decide whether this fits an 8 GB board. Run a prompt through it, then:

  ollama ps                 # resident size while loaded
  ollama show ${model}      # parameters, quantisation, and whether vision is offered

Under roughly 3 GB resident is comfortable here. ${resident:+Currently loaded: ${resident}}

If it reads nearer 5 GB, three levers remain, in the order worth trying:

  1. zram, for compressed swap in RAM instead of on the card:
       sudo apt-get install -y zram-tools
       echo 'ALGO=zstd
PERCENT=50' | sudo tee /etc/default/zramswap
       sudo systemctl restart zramswap
     This gives Chromium's idle pages somewhere cheap to go. Do not let model
     weights swap to the SD card — that turns generation into minutes.
  2. Drop the Chromium kiosk and drive the UI from another machine's browser.
     Worth about 1.5 GB: systemctl disable --now manny-kiosk
  3. A 16 GB board, or a smaller tag in MANNY_OLLAMA_MODEL.

Then run install_systemd.sh and enable manny-core and manny-kiosk explicitly.
EOF
