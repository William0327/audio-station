# Release acceptance

The repository can run CPU tests and Compose/controller smoke checks on GitHub-hosted Linux runners. That is insufficient to certify GPU inference. Before publishing a stable v1:

- On clean Ubuntu 22.04 and 24.04 NVIDIA hosts run the installer twice, with no `.env` on the first run. Verify unchanged token/volumes on the second run and no AI workloads launched.
- Install each tool independently from Setup, verify it remains stopped, and verify both pinned images build. Restart gateway mid-install, retry, and confirm no container/data replacement.
- Install catalogue models, observe byte progress and verified hashes. Interrupt a download, simulate a mismatch and low disk, retry, and verify existing unrelated models remain intact.
- Start separator, process a short local audio fixture, queue a second job, play/seek/download stems and ZIP. Cancel queued/running jobs; verify correct metadata and no remaining GPU processes.
- Start Applio with inference essentials and a trusted local RVC voice model, perform conversion, stop it, and verify VRAM is released while the controller stays online.
- Kill/restart controller, gateway, and workloads separately during jobs; verify orphan inference is stopped before another execution. Restart Docker with workloads stopped and verify they remain stopped.
- Attach an existing installation in external mode; confirm no image, network, mount, directory ownership, model, or configuration replacement. Verify old job metadata remains readable.
- Back up and restore named volumes, upgrade control services, and roll back to the previous release. Confirm data survives.
- Run CI, review dependency/image vulnerability reports and licenses, scan tracked source for personal paths/secrets/audio/models, and capture validated image digests. Publish a signed/versioned tag and release notes only after checks pass.
