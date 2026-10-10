"""Check tracked source when Git is present; otherwise check the source allowlist."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = {'README.md','LICENSE','VERSION','CHANGELOG.md','SECURITY.md','install.sh',
       'compose.yaml','.env.example','.gitignore','.dockerignore','.gitattributes','requirements-dev.txt'}
DIRS = {'controller','deploy','scripts','tests','docs','.github'}
BINARY = {'.onnx','.pth','.pt','.ckpt','.index','.bin','.wav','.mp3','.flac','.ogg','.m4a','.sqlite','.sqlite3','.pyc'}


def source_files():
    result = subprocess.run(['git','ls-files','-z'], cwd=ROOT, capture_output=True)
    if result.returncode == 0 and result.stdout:
        return [ROOT / p.decode() for p in result.stdout.split(b'\0') if p]
    return [p for p in ROOT.rglob('*') if p.is_file() and
            (p.relative_to(ROOT).parts[0] in DIRS or p.relative_to(ROOT).as_posix() in TOP)
            and '__pycache__' not in p.parts]


def check(files):
    failures = []
    personal = re.compile(r'[A-Za-z]:[\\/]Users[\\/]|' + '/' + 'home' + r'/[^\s/]+/|' + '/' + 'Users' + r'/[^\s/]+/')
    credential = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{35,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
    for file in files:
        name = file.relative_to(ROOT).as_posix() if file.is_relative_to(ROOT) else file.name
        if file.suffix.lower() in BINARY or file.name == '.env' or file.name.startswith('.env.') and file.name != '.env.example':
            failures.append(name + ': generated/secret asset must not be released')
            continue
        if file.suffix.lower() in {'.png', '.jpg', '.jpeg', '.ico'}:
            continue  # Static branding assets are binary, not source text.
        text = file.read_text(encoding='utf-8')
        if personal.search(text) or credential.search(text):
            failures.append(name + ': personal path or credential pattern')
    return failures


if __name__ == '__main__':
    problems = check(source_files())
    for problem in problems:
        print(problem, file=sys.stderr)
    print('Release source hygiene: ' + ('FAILED' if problems else 'passed'))
    sys.exit(bool(problems))
