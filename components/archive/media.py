"""Small CPU-side previews; never retain a decoded video file in memory."""
import math
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw


def indices(count, maximum):
    if count < 1:
        raise ValueError('The connected media has no video frames.')
    samples = min(maximum, count)
    return sorted(set(round(i * (count - 1) / max(1, samples - 1)) for i in range(samples)))


def valid_fps(value):
    fps = float(value)
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError('Video FPS must be a positive finite number.')
    return fps


def image_from_tensor(tensor):
    pixels = np.clip(tensor.detach().cpu().numpy() * 255, 0, 255).astype(np.uint8)
    return Image.fromarray(pixels).convert('RGB')


def frame_preview(images, fps, maximum, resolution):
    count = len(images)
    chosen = indices(count, maximum)
    fps = valid_fps(fps)
    width, height = int(images.shape[2]), int(images.shape[1])
    frames = []
    for index in chosen:
        image = image_from_tensor(images[index])
        image.thumbnail((resolution, resolution), Image.Resampling.LANCZOS)
        frames.append((index, index / fps, image))
    return make_sheet(frames, width, height, resolution), {
        'width': width, 'height': height, 'frame_count': count, 'fps': fps,
        'duration_seconds': count / fps, 'preview_frame_indices': chosen,
        'preview_timestamps': [index / fps for index in chosen],
        'duration_source': 'frame_count / fps',
    }


def file_preview(path, maximum, resolution, fallback_fps):
    # First pass counts real decoded frames without converting or retaining them.
    count, first_time, last_time, last_duration = 0, None, None, 0
    with av.open(str(path), mode='r') as container:
        if not container.streams.video:
            raise ValueError('The selected file contains no video stream.')
        stream = container.streams.video[0]
        rate = stream.average_rate or stream.guessed_rate
        fps = valid_fps(rate if rate else fallback_fps)
        for frame in container.decode(stream):
            count += 1
            if first_time is None:
                first_time = float(frame.time) if frame.time is not None else 0
            last_time = float(frame.time) if frame.time is not None else (count - 1) / fps + first_time
            last_duration = float(frame.duration * frame.time_base) if frame.duration and frame.time_base else 1 / fps
            width, height = frame.width, frame.height
    chosen = indices(count, maximum)
    frames = []
    selected = set(chosen)
    with av.open(str(path), mode='r') as container:
        stream = container.streams.video[0]
        for index, frame in enumerate(container.decode(stream)):
            if index in selected:
                timestamp = max(0, float(frame.time) - first_time) if frame.time is not None else index / fps
                image = frame.to_image().convert('RGB')
                # Respect display rotation for phone/native video files.
                if frame.rotation:
                    image = image.rotate(-float(frame.rotation), expand=True)
                width, height = image.size
                image.thumbnail((resolution, resolution), Image.Resampling.LANCZOS)
                frames.append((index, timestamp, image))
            if index >= chosen[-1]:
                break
    if len(frames) != len(chosen):
        raise ValueError('The video changed or could not be decoded completely while archiving.')
    return make_sheet(frames, width, height, resolution), {
        'width': width, 'height': height, 'frame_count': count, 'fps': fps,
        'duration_seconds': max(0, last_time - first_time + last_duration),
        'preview_frame_indices': chosen, 'preview_timestamps': [item[1] for item in frames],
        'duration_source': 'decoded video timestamps', 'video_path': str(path),
    }


def make_sheet(frames, width, height, resolution):
    columns = min(3, len(frames))
    cell_width = max(1, min(resolution // columns, width))
    cell_height = max(1, round(cell_width * height / width))
    rows = math.ceil(len(frames) / columns)
    sheet = Image.new('RGB', (cell_width * columns, (cell_height + 24) * rows), '#202326')
    draw = ImageDraw.Draw(sheet)
    for slot, (index, timestamp, image) in enumerate(frames):
        x, y = (slot % columns) * cell_width, (slot // columns) * (cell_height + 24)
        image = image.resize((cell_width, cell_height), Image.Resampling.LANCZOS)
        sheet.paste(image, (x, y))
        draw.text((x + 3, y + cell_height + 5), f'{index + 1} | {timestamp:.2f}s', fill='#ffffff')
    return sheet


def resolve_video_path(raw, roots):
    """Only local files within ComfyUI media directories may be opened."""
    roots = [Path(root).resolve() for root in roots]
    value = Path(raw).expanduser()
    candidates = [value] if value.is_absolute() else [root / value for root in roots]
    for candidate in candidates:
        path = candidate.resolve()
        if any(path.is_relative_to(root) for root in roots) and path.is_file():
            return path
    raise ValueError('Video file not found inside ComfyUI input/output/temp. Connect Load Video → VIDEO or Video Combine → filenames, or use a local file in those folders.')
