# Audio Station

A lightweight, self-hosted AI audio workstation for Linux and NVIDIA GPUs. FastAPI, vanilla HTML/CSS/JavaScript, Docker, and a persistent SQLite queue. No frontend build pipeline, cloud service, or GPU allocation in the controller.

**Release candidate: 1.0.0-rc.1.** Managed provisioning and CPU regression tests are implemented. Real Linux/NVIDIA image builds, inference, and memory-release acceptance must pass before a stable release; see [release checklist](docs/release-checklist.md).

## Quick start

Clone this repository at your chosen release, enter its directory, then:

```bash
bash install.sh
```

Open [localhost:8080](http://localhost:8080), choose **Setup & models**, and install Audio Separator or Applio independently. Install a curated model bundle, then explicitly start the tool. No container names, network names, or filesystem paths need manual configuration in managed mode.

Separator models include **UVR MDX Karaoke 2** and **BS-RoFormer Viperx 1297**. Install Viperx 1297 from Setup & models (about 610 MiB for its checkpoint and matching configuration), then select it in the separation tab. Downloads require your approval and checksum verification; no weights are included in the repository.

Requires Ubuntu 22.04/24.04 x86_64, local rootful Docker with Compose 2.24+, Python 3.10+, NVIDIA Container Toolkit, NVIDIA driver 570.124.06+, and at least 30 GiB free. The installer validates prerequisites with actionable errors; it does not install system drivers/packages or overwrite existing directories. [Installation guide](docs/installation.md).

## What it does

- Keep the control panel online while independent GPU tools start/stop on demand.
- Provision pinned Audio Separator and Applio images through a narrow, authenticated Docker gateway. Installation leaves tools stopped.
- Separate uploaded audio with installed local models; queue jobs, cancel, inspect logs, listen to stems, download individual files or ZIPs, and manage history.
- Open Applio's existing voice-conversion UI without rebuilding it.
- Install only explicitly approved catalogue models with byte progress, SHA256 verification, atomic writes, and persistent caches.
- Preserve existing installations through advanced external-container mode; no automatic adoption or directory migration.

## Architecture

```text
Browser -> CPU controller (FastAPI + SQLite audio jobs)
                   -> private authenticated Docker gateway
                        |-- durable installation queue / curated downloads
                        |-- managed labelled containers OR allowlisted external containers
                        |-- Audio Separator (on demand)
                        `-- Applio (on demand; existing UI)
```

Only the gateway sees the Docker socket. No API accepts arbitrary images, commands, mounts, or download URLs. Normal Compose startup excludes optional AI workload profiles. Persistent named volumes hold job metadata, installation metadata, uploaded audio, outputs, models, and Applio data. Localhost is the default binding; this is a private single-user app, with no public authentication service.

## Documentation

- [Install and first-run setup](docs/installation.md)
- [Migrate an existing installation](docs/migration.md)
- [Update, back up, and roll back](docs/upgrading.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Pinned upstream versions and model trust](docs/upstreams.md)
- [Release acceptance](docs/release-checklist.md), [changelog](CHANGELOG.md), [security](SECURITY.md)

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python scripts/check_release.py
.venv/bin/python -m uvicorn controller.app:app --host 127.0.0.1 --port 8080
```

Run one controller process/worker per installation. Without a configured gateway the local UI reports setup unavailable rather than simulating AI tools. CI tests lifecycle isolation, installer checks/idempotency, models/checksums, installation recovery, and audio job persistence/recovery. CI also validates Compose and builds/smoke-tests the CPU control services; GPU acceptance is documented separately.

Contributions should keep the frontend buildless and the gateway API narrow. Add a tool specification/adapter, a pinned build context, persistent-volume mapping, and tests when extending lifecycle management. Do not commit `.env`, credentials, databases, model weights, audio, build caches, or personal workstation paths. Source hygiene CI checks the tracked release files.

Licensed under [MIT](LICENSE). Upstream applications and model assets retain their own licenses and terms.
