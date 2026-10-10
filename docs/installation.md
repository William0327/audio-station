# Installation

## Supported v1 environment

Ubuntu 22.04 or 24.04, x86_64, Python 3.10+, local rootful Docker Engine with Compose plugin 2.24+, an NVIDIA CUDA-capable GPU, NVIDIA Container Toolkit configured for Docker, driver 570.124.06 or newer, and at least 30 GiB free on the repository and Docker storage filesystems. Allow more space for audio, models, and build caches. Internet access is needed for the first builds and explicitly requested models; normal separation uses local files.

Install [Docker Engine](https://docs.docker.com/engine/install/ubuntu/), the [NVIDIA driver](https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/), and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) from their official instructions. The installer validates these dependencies; it does not silently change system packages, permissions, drivers, or Docker configuration. The driver floor follows [CUDA 12.8 Update 1](https://docs.nvidia.com/cuda/archive/12.8.0/cuda-toolkit-release-notes/index.html).

Clone your chosen Audio Station release, enter its directory, then run:

```bash
bash install.sh
```

No manual container, network, or path configuration is required in managed mode. The installer generates a private `.env` token, creates labelled persistent volumes, initializes only the roots of newly owned empty writable volumes, builds the CPU controller image, and waits for health. It starts only controller and gateway. Re-running it preserves configuration, volumes, workload containers, and their runtime state. `bash install.sh --check` runs preflight only; its temporary GPU probe may pull the official CUDA image.

Open [localhost:8080](http://localhost:8080), then **Setup & models**:

1. Install Audio Separator, Applio, or both. Each builds a pinned local image. Build output appears in Installation activity; byte percentages are shown only for model downloads.
2. Install UVR MDX Karaoke 2 for separation, or Applio inference essentials for voice conversion. Review publisher terms and confirm each download. Checksums are verified before files become usable. A retry verifies existing files instead of redownloading them.
3. Start a tool explicitly. Installing it does not run it or reserve GPU memory.
4. Separate audio in the Audio Separator workspace, or open the existing Applio interface. Bring your own consented RVC voice models via Applio; Audio Station does not offer arbitrary model URLs or untrusted voice-model downloads.
5. Stop idle tools. The controller remains online.

For a remote Linux host, use `ssh -L 8080:localhost:8080 -L 6969:localhost:6969 user@host`, then open localhost in your browser. Default ports bind only to loopback. A private/Tailscale interface can be configured in `.env` with an explicit private IPv4 address, `APPLIO_PUBLIC_URL`, and host firewall rules. The app has no public login and is intended for one trusted user. Do not expose it publicly.

## Persistent storage

Default volume names begin with `audio-station-`: `data` (jobs SQLite), `state` (installation SQLite), `input`, `output`, `models`, `applio-models`, `applio-assets`, `applio-logs`, and `applio-cache`. Model weights and generated audio stay in these volumes, outside source code. Existing installation files can be attached through advanced external mode; see [migration](migration.md).

The separator gets a read-only model cache. Applio's prerequisite autoloader is disabled by the managed launcher; inference essentials are installed via the explicit catalogue. Applio retains its upstream interface and may offer its own network features; downloads initiated there are governed by that application. Training pretrained bundles, TTS downloads, and arbitrary third-party embedder downloads are outside the curated v1 catalogue.

The controller runs as UID 10001 / GID 0, without Linux capabilities, and creates each managed job output directory with group write access. The gateway and workload can write stems/logs there while the controller can archive and delete completed sessions. The gateway also drops capabilities; it never recursively changes filesystem ownership. External cache permissions may need an explicitly granted narrow ACL for these users/groups.

## Optional Compose profiles

`separator` and `applio` profiles mirror the gateway's fixed definitions for maintenance. Ordinary `docker compose up` excludes them. For advanced manual provisioning, `docker compose --profile separator build separator` followed by `docker compose --profile separator create separator` leaves it stopped. Prefer the UI for normal setup. Do not combine managed profiles with external mode. The controller installer never activates workload profiles.
