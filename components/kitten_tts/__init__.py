import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import wave

import numpy as np
import torch
import folder_paths

RUNTIME = Path(os.environ.get('DHARANI_PROD_KITTEN_HOME', str(Path.home() / 'Apps' / 'KittenTTS'))).expanduser()


class VallpaperKittenClone:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'reference_audio': ('AUDIO',),
            'text': ('STRING', {'multiline': True, 'default': 'I built Prompt Archive for Comfy U I. Let me show you how it works.'}),
            'reference_text': ('STRING', {'multiline': True, 'default': '', 'tooltip': 'Exact words spoken in the reference. Required so generation stays offline.'}),
            'device': (['cuda', 'cpu'],),
        }}

    RETURN_TYPES = ('AUDIO', 'STRING')
    RETURN_NAMES = ('audio', 'saved_path')
    FUNCTION = 'generate'
    CATEGORY = 'dharani.prod/audio'
    DESCRIPTION = 'Kitten TTS 2 voice cloning in a separate local environment. Uses your AUDIO reference, not a preset voice.'

    def generate(self, reference_audio, text, reference_text, device):
        if not text.strip():
            raise ValueError('Enter the narration text.')
        if not reference_text.strip():
            raise ValueError('Enter the exact words spoken in your reference audio.')
        python = RUNTIME / '.venv2' / 'Scripts' / 'python.exe'
        if not python.is_file():
            raise RuntimeError('Kitten TTS 2 runtime is not installed.')
        root = Path(folder_paths.get_output_directory()) / 'vallpaper_kitten'
        root.mkdir(parents=True, exist_ok=True)
        stem = root / ('clone-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
        samples = reference_audio['waveform'][0].detach().cpu().float().mean(dim=0).numpy()
        sr = int(reference_audio['sample_rate'])
        if not 5 <= len(samples) / sr <= 30:
            raise ValueError('Use a clean reference between 5 and 30 seconds long.')
        reference = stem.with_suffix('.reference.wav')
        with wave.open(str(reference), 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(sr)
            out.writeframes((np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes())
        target = stem.with_suffix('.wav')
        request = stem.with_suffix('.json')
        request.write_text(json.dumps({'text': text, 'reference': str(reference), 'reference_text': reference_text, 'output': str(target), 'device': device}), encoding='utf-8')
        log_path = stem.with_suffix('.log')
        from comfy.model_management import throw_exception_if_processing_interrupted
        with log_path.open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(python), '-u', str(Path(__file__).with_name('worker.py')), str(request)], stdout=log, stderr=subprocess.STDOUT, env={**os.environ, 'PYTHONIOENCODING': 'utf-8'}, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                while process.poll() is None:
                    throw_exception_if_processing_interrupted()
                    time.sleep(0.3)
            except BaseException:
                process.terminate()
                process.wait(timeout=30)
                raise
        if process.returncode or not target.is_file():
            raise RuntimeError('Kitten TTS failed: ' + log_path.read_text(encoding='utf-8', errors='replace')[-2500:])
        with wave.open(str(target), 'rb') as audio:
            rate, channels = audio.getframerate(), audio.getnchannels()
            data = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
        return {'waveform': torch.from_numpy(data.reshape(-1, channels).T.copy()).unsqueeze(0), 'sample_rate': rate}, str(target)


NODE_CLASS_MAPPINGS = {'VallpaperKittenClone': VallpaperKittenClone}
NODE_DISPLAY_NAME_MAPPINGS = {'VallpaperKittenClone': 'dharani.prod Kitten TTS 2 Clone'}
