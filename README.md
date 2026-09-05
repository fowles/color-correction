# underwater-color

Underwater photo and video color correction: closed-form and learned methods,
numpy in and numpy out for stills, one clip-wide ffmpeg filter for video.

Extracted from [photogen](https://github.com/mfk/photogen). Full method menu
and rationale land in Task 8 of the extraction.

## Install

    uv add underwater-color            # closed-form methods
    uv add "underwater-color[dicam]"   # adds the learned DICAM method (torch)

Video requires `ffmpeg` and `ffprobe` on PATH (`brew install ffmpeg`).
