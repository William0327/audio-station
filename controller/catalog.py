"""Release-reviewed download allowlist. URLs never come from API inputs.

SHA256 values were independently streamed from pinned publisher assets.
Model licensing/consent is distinct from Audio Station's own MIT license.
"""
HF = 'https://huggingface.co/IAHispano/Applio/resolve/70ed563897504c756ec94067c12c902c4fd42025/Resources/'
SEPARATOR_MODELS = 'https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs/'
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
    'bs-roformer-viperx-1297': {
        'title': 'BS-RoFormer Viperx 1297', 'tool': 'separator',
        'publisher': 'Viperx / audio-separator model repository',
        'source': 'https://github.com/nomadkaraoke/python-audio-separator/releases/tag/model-configs',
        'license_note': 'Review the publisher terms before use; model rights are separate from the controller license.',
        'model_filename': 'model_bs_roformer_ep_317_sdr_12.9755.ckpt',
        'files': [
            dict(path='model_bs_roformer_ep_317_sdr_12.9755.yaml', size=2273,
                 url=SEPARATOR_MODELS+'model_bs_roformer_ep_317_sdr_12.9755.yaml',
                 sha256='2bfdd16c656bd9519aba757cc4f8834b7ede675eb1e00ec4772d74ae1c41af7f'),
            dict(path='model_bs_roformer_ep_317_sdr_12.9755.ckpt', size=639331213,
                 url=SEPARATOR_MODELS+'model_bs_roformer_ep_317_sdr_12.9755.ckpt',
                 sha256='5b84f37e8d444c8cb30c79d77f613a41c05868ff9c9ac6c7049c00aefae115aa'),
        ],
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
