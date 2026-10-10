"""Release-reviewed download allowlist. URLs never come from API inputs.

SHA256 values were independently streamed from pinned publisher assets.
Model licensing/consent is distinct from Audio Station's own MIT license.
"""
HF = 'https://huggingface.co/IAHispano/Applio/resolve/70ed563897504c756ec94067c12c902c4fd42025/Resources/'
CATALOG = {
    'uvr-karaoke': {
        'title': 'UVR MDX Karaoke 2', 'tool': 'separator',
        'publisher': 'TRvlvr / Ultimate Vocal Remover',
        'source': 'https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models',
        'license_note': 'Review the publisher terms before use; model rights are separate from the controller license.',
        'files': [dict(path='UVR_MDXNET_KARA_2.onnx', size=52786726,
                       url='https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/UVR_MDXNET_KARA_2.onnx',
                       sha256='bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4')],
    },
    'applio-essentials': {
        'title': 'Applio inference essentials', 'tool': 'applio',
        'publisher': 'IAHispano / Applio',
        'source': 'https://huggingface.co/IAHispano/Applio/tree/70ed563897504c756ec94067c12c902c4fd42025/Resources',
        'license_note': 'Official inference dependencies, not a voice model. Review upstream asset terms. Supply your own consented voice models in Applio.',
        'files': [
            dict(path='predictors/rmvpe.pt', size=181184272, url=HF+'predictors/rmvpe.pt', sha256='6d62215f4306e3ca278246188607209f09af3dc77ed4232efdd069798c4ec193'),
            dict(path='predictors/fcpe.pt', size=43362881, url=HF+'predictors/fcpe.pt', sha256='8544427eebbf2baef6213cc9a05057e46961617a8e5bd96975a0d42da6a09059'),
            dict(path='embedders/contentvec/pytorch_model.bin', size=378342945, url=HF+'embedders/contentvec/pytorch_model.bin', sha256='d8dd400e054ddf4e6be75dab5a2549db748cc99e756a097c496c099f65a4854e'),
            dict(path='embedders/contentvec/config.json', size=1388, url=HF+'embedders/contentvec/config.json', sha256='2ddde063b795d38d9051a7215a092fecf4cfe148b54251e38de51d88d356898b'),
        ],
    },
}
