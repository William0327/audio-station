# Preserve an existing workstation

The managed installer does not scan, move, rename, delete, or adopt arbitrary host model directories. Use external mode to retain a working installation unchanged.

External mode probes the NVIDIA toolkit with a plain official Ubuntu image, rather than imposing managed CUDA 12.8.1's driver floor on an existing working tool. Your external images remain responsible for their own driver compatibility.

1. Stop submissions and let active jobs finish. Back up existing Compose files, configuration, job metadata, and audio/model data. Run `bash scripts/inspect-host.sh /path/to/existing/project` for a read-only inventory; inspect its launch commands and mounts locally.
2. Copy `.env.example` to `.env` and set `DEPLOYMENT_MODE=external`. Set exact existing container names, existing Docker network and `WORKLOAD_NETWORK_EXTERNAL=true`. Set `HOST_INPUT_DIR`, `HOST_OUTPUT_DIR`, and `HOST_MODELS_DIR` to existing absolute Linux directories or named Docker volumes, and `HOST_DATA_DIR` to the existing controller metadata directory if retaining history. Set corresponding `SEPARATOR_*_DIR` paths as seen inside the existing separator and its CLI executable. Set Applio health and browser URLs.
3. Keep the existing gateway token or leave it empty for the installer to generate one. Do not publish `.env`. No installer step sources it as executable shell.
4. Run `bash install.sh`. The installer verifies explicit external paths/volumes exist and never changes their ownership or contents. The controller still needs UID 10001 read/write access to its metadata and input/output files. Grant a narrow shared-group ACL yourself if needed; preserve existing owners and models. The existing job schema is retained without destructive migration.
5. Stop the old controller after the new one is healthy. Never run two controller workers against the same job database. Existing workload containers are controlled by exact name; external mode offers no installation, removal, image replacement, or model-write API.

The previous development Compose file was named `compose.controller.yaml`. The release uses `compose.yaml`. Keep your old file and configuration in a backup; do not run an old project's `down -v`. If you used the old `audio-control` project, stop its controller/gateway explicitly before the new controller uses the same database. Existing workload containers and their external network are not recreated.

To move later to managed storage, make a separate backup/copy and verify checksums before configuring the new instance. No automated directory takeover exists in v1. A container or default volume with the same name but no matching ownership label is rejected, rather than adopted. Choose another `STATION_INSTANCE` or explicitly configure the existing storage. Model removal always requires confirmation and is limited to catalogue files whose content matches the catalogue checksum; other files and directories are preserved.
