"""Fixed single-file conversion entry point; invoked only by the restricted gateway."""
import json
import os
import sys
from pathlib import Path


def convert(payload):
    os.chdir('/app')
    sys.path.insert(0, '/app')
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    required = ['predictors/rmvpe.pt','predictors/fcpe.pt',
                'embedders/contentvec/pytorch_model.bin','embedders/contentvec/config.json']
    if any(not (Path('/app/rvc/models')/name).is_file() for name in required):
        raise RuntimeError('Install the Applio inference essentials bundle in Setup before conversion')
    from core import run_infer_script
    settings = payload['options']
    output = Path(payload['output'])
    result = run_infer_script(
        pitch=settings['pitch'], index_rate=settings['index_rate'],
        volume_envelope=settings['volume_envelope'], protect=settings['protect'],
        f0_method=settings['f0_method'], input_path=payload['input'],
        output_path=str(output.with_suffix('.wav')), pth_path=payload['model'],
        index_path=payload['index'], split_audio=False, f0_autotune=False,
        f0_autotune_strength=1, proposed_pitch=False, proposed_pitch_threshold=155,
        clean_audio=False, clean_strength=0.5, export_format=payload['format'],
        embedder_model='contentvec',
    )
    if not output.is_file() or not output.stat().st_size:
        raise RuntimeError('Applio produced no converted audio; inspect the preceding log')
    print(result, flush=True)


if __name__ == '__main__':
    convert(json.loads(sys.argv[1]))
