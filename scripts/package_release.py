"""Create a source-only release archive. Never packages local runtime data."""
import hashlib
import tarfile
from pathlib import Path
from scripts.check_release import ROOT, source_files, check


def package(destination):
    files=source_files()
    failures=check(files)
    if failures:
        raise RuntimeError('\n'.join(failures))
    if any(path.is_symlink() for path in files):
        raise RuntimeError('Release source cannot contain symlinks')
    version=(ROOT/'VERSION').read_text().strip()
    destination.mkdir(parents=True,exist_ok=True)
    archive=destination/f'audio-station-{version}.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        for path in sorted(files):
            info=tar.gettarinfo(str(path),arcname=f'audio-station-{version}/'+path.relative_to(ROOT).as_posix())
            info.uid=info.gid=0
            info.uname=info.gname=''
            info.mode=0o755 if path.suffix=='.sh' else 0o644
            with path.open('rb') as handle:
                tar.addfile(info,handle)
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination/'SHA256SUMS').write_text(f'{checksum}  {archive.name}\n')
    return archive


if __name__=='__main__':
    print(package(ROOT/'release'))
