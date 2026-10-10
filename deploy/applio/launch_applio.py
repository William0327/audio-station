"""Use upstream UI, with prerequisite downloads handled by the curated catalogue."""
import os
import runpy
import sys
from pathlib import Path

os.chdir('/app')
sys.path.insert(0, '/app')
required = ['predictors/rmvpe.pt', 'predictors/fcpe.pt',
            'embedders/contentvec/pytorch_model.bin', 'embedders/contentvec/config.json']
if any(not (Path('/app/rvc/models') / name).is_file() for name in required):
    raise SystemExit('Install the Applio inference essentials bundle from Audio Station Models before starting.')
import core
core.run_prerequisites_script = lambda *args, **kwargs: None
sys.argv = ['app.py', '--server-name', '0.0.0.0', '--port', '6969']
runpy.run_path('/app/app.py', run_name='__main__')
