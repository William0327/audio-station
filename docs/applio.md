# Applio voice conversion

In managed mode, open **Applio** in the sidebar. Install Applio and its inference essentials in Setup first. The original **Advanced Applio UI** remains available from Overview for training and other upstream features.

## Import your voice

1. In **Your voice library**, choose an RVC inference `.pth` model and optionally its matching `.index`. You can import indexes separately. ZIP archives and training checkpoints are not supported.
2. Confirm that you trust the file's source and have permission to use the voice, then select **Import selected files**. A model may execute code when loaded by upstream PyTorch; upload acceptance and transfer checksums do not certify its safety or compatibility.
3. Select the imported model and its matching index in the conversion form. The optional index improves retrieval for the corresponding model; indexes are not interchangeable between voices.

Uploads stream to temporary input storage and are copied with SHA256 verification into unique directories under `audio-station-imports` in the existing Applio logs volume. Existing files are never overwritten or deleted. The gateway never deserializes imported files. Existing inference models and indexes elsewhere in that volume are listed too; `G_`/`D_` training checkpoints and symlinks are excluded.

The default per-file import limit is 2048 MiB (`MAX_VOICE_IMPORT_MB` in `.env`); audio uses the separate `MAX_UPLOAD_MB` limit. Import needs room for both the staged and stored file. Refresh the library after a connection interruption before retrying; a completed import may already be present.

## Convert audio

Start Applio explicitly, choose input audio, a voice model, optional index, pitch shift, and output format, then choose **Convert audio**. Advanced settings include RMVPE/FCPE pitch detection, index strength, consonant protection, and volume envelope. Multi-speaker models use speaker 0 in this first integration. Additional embedders, batch inference, training, and effects remain in the upstream UI.

From a completed separation, select **Convert in Applio** beside a stem to use it as the source. Audio Station retrieves that stem through its existing download endpoint and uploads it as a new independent conversion job; deleting the original session after submission does not remove the conversion input.

Separation and conversion share a durable single-worker queue. Existing jobs migrate with `tool=separator`; previous history and volumes remain intact. Progress uses queued/running/completed states and logs, not estimated percentages. Playback, downloads, ZIPs, cancellation, and deletion work for both job types. Stopping a tool cancels its running and queued jobs only. Controller/gateway failures trigger a stop of the affected workload before another job is dispatched.

Each conversion runs in a separate process inside the managed Applio container. The controller stays CPU-only. Audio Station serializes its own jobs, but cannot coordinate jobs started directly from the upstream UI; avoid simultaneous inference/training there. Stopping Applio interrupts both interfaces.

Integrated inference and imports require managed mode. External installations retain their original interface and mappings.

## Update an existing Applio installation

The integration requires workload image `audio-station/applio:3.5.1-2`, its bundled conversion wrapper, and shared input/output mounts. Updating only the controller does not modify an existing workload container.

Finish jobs, stop Applio in the UI, and back up persistent volumes as described in [upgrading](upgrading.md). Update the repository and controller/gateway, verify the stopped Applio container is yours, then remove only that container:

```bash
docker compose up -d --build controller gateway
docker inspect audio-station-applio --format '{{json .Config.Labels}}'
docker rm audio-station-applio
```

Replace the name for a custom `STATION_INSTANCE`. Do not use `-v`. Reinstall Applio from Setup and start it when ready. The inference essentials, existing voice models, logs, assets, and caches remain in their persistent volumes. Setup deliberately refuses to replace an existing container running the previous image revision.
