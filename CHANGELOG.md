# Changelog

## Unreleased

- Integrated Applio inference, voice model/index uploads, and separation-to-conversion handoff.
- Shared durable queue, tool-specific cancellation/recovery, and backward-compatible job migration.
- Applio workload image revision 3.5.1-2 adds the conversion wrapper and input/output mounts; existing containers require an explicit update.

## 1.0.0-rc.1

- Managed, stopped-by-default installation of Audio Separator and Applio.
- Advanced external-container compatibility without data takeover.
- Single Compose deployment, persistent volumes, Linux/NVIDIA preflight installer.
- First-run Setup, durable installation operations, curated checksummed model catalogue.
- Existing persistent audio queue, cancellation, recovery, playback/downloads retained.
- Release documentation, MIT license, source hygiene checks, and Linux CI.

This candidate requires real Linux/NVIDIA acceptance before promotion to stable.
