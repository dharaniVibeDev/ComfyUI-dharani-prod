import json
import os
from pathlib import Path
import sys

runtime = Path(os.environ.get('DHARANI_PROD_KITTEN_HOME', str(Path.home() / 'Apps' / 'KittenTTS'))).expanduser()
os.environ['HF_HOME'] = os.environ.get('DHARANI_PROD_KITTEN_CACHE', str(runtime / 'kitten2-cache'))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

if __name__ == '__main__':
    import torch
    import soundfile as sf
    from kittenml import KittenTTS
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    torch.set_num_threads(6)
    model = KittenTTS('KittenML/kitten-tts-2', device=request['device'])
    options = {'reference': request['reference']}
    if request['reference_text'].strip():
        options['reference_text'] = request['reference_text']
    audio = model.generate(request['text'], **options)
    sf.write(request['output'], audio, model.sample_rate, subtype='PCM_16')
    print('Saved ' + request['output'], flush=True)
