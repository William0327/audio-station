# Upgrades and backups

Audio Station uses semantic versions in `VERSION`; this tree is **1.0.0-rc.1**, a release candidate pending the Linux/GPU acceptance checklist. No GitHub release has been published by this change. Upstream tool versions and local image revision tags are documented in [upstreams](upstreams.md).

For maintainers: update `VERSION`, the controller image version in Compose, pins and changelog together. Run `python -m scripts.package_release` to produce a source-only archive and `SHA256SUMS`. A matching `v<version>` Git tag runs the release-artifact workflow; it does not publish a GitHub release automatically. Attach those verified artifacts to the reviewed release after acceptance.

Before upgrading, finish audio jobs and installation operations and stop both AI workloads using the UI. Back up `.env` privately, all persistent volumes, and any external directories. For consistent SQLite backups stop the controller and gateway first:

```bash
docker compose stop controller gateway
```

Use a trusted Docker volume backup tool or copy volumes from a temporary read-only-mounted utility container. Include jobs, inputs, results, and all model/config caches. Keep the original volume names and `STATION_INSTANCE`; changing them selects a different installation.

Check out the desired tagged release and run `bash install.sh`. It rebuilds and updates only controller/gateway, reuses configuration and volumes, and does not pull, rebuild, recreate, or start AI tools. Roll back by restoring the previous release and its matching metadata backup, then running the installer. No destructive schema migrations are included in this candidate.

Tool updates are deliberately explicit. If a new release pins a different workload image, Setup refuses to replace the existing container. After a backup and a clean stop, inspect its `io.audio-station.managed` and `io.audio-station.tool` labels, then remove **only that stopped managed container** with `docker rm <verified-name>` (without `-v`). Use Setup to install its new pinned image; persistent volumes survive. External containers are upgraded through their owner's existing process.

Do not use `docker compose down -v`, `docker volume prune`, or model-directory replacement as an update strategy. Named volumes survive normal container updates and removal but not explicit volume deletion. An interrupted model download is discarded on handled failure; after a hard kill a `.station-part` file may remain. Inspect and remove only that partial file before retrying; never delete a whole model directory.

Applio image revision `3.5.1-2` adds integrated conversion and new mounts. Follow the [Applio update steps](applio.md#update-an-existing-applio-installation) for an existing installation. The job database adds tool/options columns while preserving old rows.
