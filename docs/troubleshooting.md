# Troubleshooting

| Symptom | Action |
| --- | --- |
| Docker permission denied | Verify `docker info` works for the installer user. Configure Docker access following its official Linux post-install guidance; do not chmod the Docker socket to world-writable. |
| Missing Compose or old version | Install/update the Docker Compose v2 plugin to 2.24+. `docker-compose` v1 is unsupported. |
| GPU probe fails / could not select device driver | Verify host `nvidia-smi`; configure NVIDIA Container Toolkit for Docker and restart Docker using NVIDIA's instructions. Rerun `bash install.sh --check`. |
| Driver too old | Update/reboot to driver 570.124.06+ for pinned CUDA 12.8.1. The installer does not change drivers itself. |
| Unsupported remote/rootless daemon | Run the installer on the Linux GPU host, with the local rootful Unix socket. Docker Desktop/WSL, ARM, AMD, and macOS are outside v1 support. |
| Disk preflight fails | Provide at least 30 GiB on repository and Docker storage filesystems. Large tool builds can need more; inspect `docker system df` before selectively clearing expendable build caches. Preserve model/data volumes. |
| Port already allocated | Choose free `CONTROLLER_PORT`/`APPLIO_PORT` values in `.env`, update `APPLIO_PUBLIC_URL`, then rerun installer. No data migration is needed. |
| Controller healthy but web port refuses connections | Run `docker compose port controller 8080`. The controller needs both the `web` bridge for port publishing and the private `control` network for gateway access. After updating Compose, run `docker compose up -d controller gateway` to recreate services without removing volumes. With the default bind address, test `http://127.0.0.1:8080/health` on the Docker host. |
| Unowned container/volume collision | Choose another `STATION_INSTANCE` or configure external mode. Never delete or relabel unknown data to force adoption. |
| Build failed | Read Setup installation activity and `docker compose logs --tail=100 gateway`. Resolve connectivity/disk/package error and retry; stopped existing containers and models are preserved. |
| Applio exits immediately | Install the Applio inference essentials bundle, then Start. Inspect `docker logs audio-station-applio` (or your configured instance's name). |
| Model checksum mismatch | Download was discarded. Retry; if a different existing file occupies the same path, back it up and resolve manually. Audio Station refuses to overwrite it. |
| Partial file after power loss | Inspect the specific `.station-part` file in the model volume and remove only that incomplete file, then retry. Existing completed files are verified and reused. |
| Restart interrupted an install | Setup marks interrupted running operations failed and preserves caches. Retry installation; container ownership/image checks and checksum verification reconcile completed work. |
| Inference failed or gateway restarted | Worker confirms a separator stop before another job; a controller restart also recovers running-job metadata. Restart the tool and submit again. Queued jobs can fail while the service is stopped. |
| No GPU readings while tools stopped | Expected: telemetry uses `nvidia-smi` inside an already-running separator and never starts a tool to collect metrics. |
| External uploads fail with permissions | UID 10001 needs metadata/input/output access. Use narrow ACLs/shared groups after backing up; installer never recursively chowns external paths. |

Diagnostics: `docker compose ps`, `docker compose logs --tail=100 controller gateway`, and individual job logs. Keep tokens, filesystem dumps, and private audio out of public issues. The gateway is intentionally unpublished. Checksum verification does not replace a model-license or trust review.
