#!/usr/bin/env bash
# Read-only inventory. Does not start, stop, build, pull, or edit anything.
set -eu
cd "${1:-.}"
printf '\nProject files (depth 2)\n'
find . -maxdepth 2 -type f \( -iname '*compose*.yml' -o -iname '*compose*.yaml' -o -iname '*dockerfile*' \) -print
printf '\nContainers and networks\n'
docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Networks}}'
printf '\nExisting container mounts and launch commands\n'
for name in $(docker ps -a --format '{{.Names}}'); do
  docker inspect --format '{{.Name}} Entrypoint={{json .Config.Entrypoint}} Cmd={{json .Config.Cmd}} Mounts={{json .Mounts}}' "$name"
done
printf '\nLocal model filenames (depth 4)\n'
find . -maxdepth 4 -type f \( -iname '*.onnx' -o -iname '*.pth' -o -iname '*.ckpt' -o -iname '*.yaml' \) -print
printf '\nGPU status\n'
nvidia-smi || true
