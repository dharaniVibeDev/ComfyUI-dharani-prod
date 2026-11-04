from pathlib import Path
import folder_paths

from .archive import Store
from .capture import capture
from .media import file_preview, frame_preview, image_from_tensor, resolve_video_path


def store():
    return Store(Path(folder_paths.get_output_directory()) / 'PromptArchive')


class PromptArchiveDOCX:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'enable_archive': ('BOOLEAN', {'default': True}),
            'workflow_label_override': ('STRING', {'default': ''}),
            'output_folder': ('STRING', {'default': 'PromptArchive', 'tooltip': 'Relative to ComfyUI output. Absolute paths must also remain inside ComfyUI output.'}),
            'filename_prefix': ('STRING', {'default': ''}),
            'preview_resolution': ('INT', {'default': 768, 'min': 128, 'max': 1536, 'step': 64}),
            'jpeg_quality': ('INT', {'default': 70, 'min': 10, 'max': 95}),
            'include_negative_prompt': ('BOOLEAN', {'default': True}),
            'include_camera_lighting': ('BOOLEAN', {'default': True}),
        }, 'optional': {
            'images': ('IMAGE', {'tooltip': 'Optional still images or decoded video frames. Not required when a video input is supplied.'}),
            'video': ('VIDEO', {'tooltip': 'Connect a native VIDEO output directly; no IMAGE connection needed.'}),
            'original_image_path': ('STRING', {'default': '', 'tooltip': 'Optional existing output image path, when known. The archive never saves a full-size image.'}),
            'archive_mode': (['auto', 'image', 'video'], {'default': 'auto', 'tooltip': 'Video inputs are detected automatically. For an IMAGE frame batch, choose video to archive it as one clip.'}),
            'video_fps': ('FLOAT', {'default': 24.0, 'min': 0.1, 'max': 1000.0, 'tooltip': 'Fallback FPS when no unambiguous upstream FPS is captured. Match your video export.'}),
            'preview_frames': ('INT', {'default': 3, 'min': 1, 'max': 6}),
            'original_video_path': ('STRING', {'default': ''}),
            'video_files': ('VHS_FILENAMES', {'tooltip': 'Optional Video Combine filenames output. Forces video mode and records the final output path.'}),
            'prompt_text': ('STRING', {'default': '', 'multiline': True, 'tooltip': 'Optional exact prompt override, useful for an existing video with no generation graph. Blank uses automatic capture.'}),
        }, 'hidden': {'prompt': 'PROMPT', 'extra_pnginfo': 'EXTRA_PNGINFO', 'unique_id': 'UNIQUE_ID'}}

    RETURN_TYPES = ()
    FUNCTION = 'save'
    CATEGORY = 'dharani.prod'
    OUTPUT_NODE = True
    DESCRIPTION = 'Connect Video Combine filenames, native VIDEO, a local video path, or IMAGE frames. Images are optional. Video inputs automatically produce one DOCX with sampled preview frames. Existing archives and workflow reload are preserved.'

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float('nan')

    def save(self, images=None, enable_archive=True, workflow_label_override='', output_folder='PromptArchive', filename_prefix='', preview_resolution=768, jpeg_quality=70, include_negative_prompt=True, include_camera_lighting=True, original_image_path='', prompt=None, extra_pnginfo=None, unique_id=None, archive_mode='auto', video_fps=24.0, preview_frames=3, original_video_path='', video_files=None, video=None, prompt_text=''):
        if not enable_archive:
            return {'ui': {'archive_records': [], 'archive_status': ['Archive disabled']}}
        root = Path(folder_paths.get_output_directory()).resolve()
        target = (root / output_folder).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Archive output folder must remain inside ComfyUI/output.')
        if not 128 <= preview_resolution <= 1536 or not 10 <= jpeg_quality <= 95:
            raise ValueError('Preview resolution or JPEG quality is outside the supported range.')
        record = capture(prompt or {}, extra_pnginfo or {}, str(unique_id), workflow_label_override)
        if prompt_text != '':
            record['positive_prompt'] = prompt_text
            record['notes'] = [note for note in record['notes'] if not note.startswith('positive_prompt:')]
            record['notes'].append('Prompt supplied explicitly through the archive prompt_text input; not verified against the original generation.')
        if original_image_path:
            record['image_path'] = original_image_path
            record['notes'] = [n for n in record['notes'] if not n.startswith('Original image path')]
        is_video = archive_mode == 'video' or video_files is not None or video is not None or bool(original_video_path)
        record['media_type'] = 'video' if is_video else 'image'
        saved = []
        if is_video:
            if not 1 <= preview_frames <= 6:
                raise ValueError('Choose between 1 and 6 preview frames.')
            path = original_video_path
            if not path and video_files is not None:
                if not isinstance(video_files, (list, tuple)) or len(video_files) != 2 or not isinstance(video_files[1], (list, tuple)):
                    raise ValueError('video_files must come from Video Combine filenames output.')
                path = str(video_files[1][-1]) if video_files[1] else ''
                if not video_files[0]:
                    record['notes'].append('Video Combine save_output is disabled; the recorded video path may be temporary.')
            if path:
                path = resolve_video_path(path, [folder_paths.get_output_directory(), folder_paths.get_input_directory(), folder_paths.get_temp_directory()])
                sheet, metadata = file_preview(path, preview_frames, preview_resolution, video_fps)
                record['preview_source'] = 'encoded video file'
            elif video is not None:
                # Native VIDEO components respect the host's trim/crop semantics.
                components = video.get_components()
                sheet, metadata = frame_preview(components.images, components.frame_rate, preview_frames, preview_resolution)
                record['preview_source'] = 'native VIDEO components'
                metadata['video_path'] = None
            elif images is not None:
                fps = record.get('fps') if record.get('fps') is not None else video_fps
                sheet, metadata = frame_preview(images, fps, preview_frames, preview_resolution)
                record['preview_source'] = 'decoded IMAGE frame batch'
                metadata['video_path'] = None
            else:
                raise ValueError('Connect Video Combine filenames to video_files, a native VIDEO to video, or decoded frames to images. A local original_video_path also works.')
            record.update(metadata)
            count, fps = record['frame_count'], record['fps']
            record['batch_size'] = count
            record['notes'] = [note for note in record['notes'] if not note.startswith('Original image path')]
            record['notes'].append(f"Preview source: {record['preview_source']}. Duration source: {record['duration_source']}. No video is copied, re-encoded, or embedded in the DOCX.")
            if not path:
                record['notes'].append('Video path unavailable: connect Video Combine filenames or set original_video_path.')
            result = store().save(record, sheet, target, filename_prefix, preview_resolution, jpeg_quality, include_negative_prompt, include_camera_lighting)
            saved.append({key: result[key] for key in ('record_id', 'docx_path', 'docx_bytes', 'workflow_name')})
            return {'ui': {'archive_records': saved, 'archive_status': [f"Saved 1 video archive ({count} frames, {record['duration_seconds']:.2f}s at {fps:g} FPS)"]}}
        if images is None:
            raise ValueError('Connect an image to images, Video Combine filenames to video_files, or a native VIDEO to video. Images are not required for video inputs.')
        record['width'], record['height'] = int(images.shape[2]), int(images.shape[1])
        record['batch_size'] = int(images.shape[0])
        database = store()
        for index, tensor in enumerate(images):
            item = dict(record, batch_index=index)
            image = image_from_tensor(tensor)
            result = database.save(item, image, target, filename_prefix, preview_resolution, jpeg_quality, include_negative_prompt, include_camera_lighting)
            saved.append({key: result[key] for key in ('record_id', 'docx_path', 'docx_bytes', 'workflow_name')})
        return {'ui': {'archive_records': saved, 'archive_status': [f'Saved {len(saved)} archive record(s)']}}


NODE_CLASS_MAPPINGS = {'PromptArchiveDOCX': PromptArchiveDOCX}
NODE_DISPLAY_NAME_MAPPINGS = {'PromptArchiveDOCX': 'dharani.prod Prompt Archive'}
