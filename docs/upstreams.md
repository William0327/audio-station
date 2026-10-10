# Pinned upstreams and trust boundary

| Component | Pin | Source |
| --- | --- | --- |
| Audio Station | 1.0.0-rc.1 | `VERSION` |
| Audio Separator | 0.47.0, source commit `c7f2a5c8c3beea1f9ec9ab7206caaebc05f45ac4` | [official release](https://github.com/nomadkaraoke/python-audio-separator/releases/tag/v0.47.0), exact PyPI package |
| Applio | 3.5.1, commit `b8791412993ebc934c148bd84798782af2f0439e` | [official release](https://github.com/IAHispano/Applio/releases/tag/3.5.1) |
| Applio source archive SHA256 | `56d30b0d39d45d6c4c3aa331b8dbd8fd1417924d29defea200643cab7c7f864f` | checked during image build |
| PyTorch / Torchaudio | 2.7.1, CUDA 12.8 wheels | [official PyTorch packages](https://download.pytorch.org/whl/cu128) |
| ONNX Runtime GPU | 1.22.0 | exact PyPI package |
| CUDA runtime | 12.8.1, cuDNN runtime, Ubuntu 24.04 | NVIDIA CUDA image |
| Applio inference catalogue | HF commit `70ed563897504c756ec94067c12c902c4fd42025` | [official publisher assets](https://huggingface.co/IAHispano/Applio/tree/70ed563897504c756ec94067c12c902c4fd42025/Resources) |

The gateway accepts only known tool IDs and catalogue IDs. It builds only bundled Docker contexts and fixed image tags, creates only ownership-labelled tool containers, and executes only the fixed separator CLI or NVIDIA query. API clients cannot choose images, mounts, devices, commands, build contexts, or download URLs. A read-only Docker socket mount still permits privileged Engine operations; isolation comes from this small authenticated gateway, its unpublished port, and its narrow code, not from the socket mount's `ro` flag. The controller has no socket and no GPU.

Model file sizes and SHA256 hashes are embedded in `controller/catalog.py`. The ONNX checksum was independently computed from the publisher's release asset, which has no published digest; Applio large-file hashes match the publisher's LFS metadata, and its config was hashed independently. Explicit installation verifies them with bounded-memory streaming and commits via a no-overwrite atomic link. Presence is detected cheaply; choose **Verify cache** to rehash existing files. No integrity claim is made for user-imported files.

These are application/runtime pins, not a fully hermetic dependency lock: upstream Python transitive dependencies and OS package repositories may change. Image builds must pass the release smoke workflow and real-GPU acceptance before a stable tag is published. Registry base images are version-tagged, not digest-pinned in this candidate. Maintainers should capture the validated image digests/SBOM alongside stable releases. Upstream applications and model weights retain their own licenses/terms; Audio Station's MIT license covers this repository's code only.
