# underwater-color

Underwater photo and video color correction: closed-form and learned methods,
numpy in and numpy out for stills, one clip-wide ffmpeg filter for video.

Extracted from [photogen](https://github.com/mfk/photogen).

## Install

    uv add underwater-color            # closed-form methods
    uv add "underwater-color[dicam]"   # adds the learned DICAM method (torch)

Video requires `ffmpeg` and `ffprobe` on PATH (`brew install ffmpeg`). They
are system binaries rather than wheels, so there is no `[video]` extra; a
missing ffmpeg is reported at runtime.

## Methods

| method | what it does |
| --- | --- |
| `channel-stretch` | Per-channel percentile histogram stretch (0.5–99.5 → 0–255), gain capped at 6.0 so a near-empty channel is not amplified into speckle. |
| `hue-shift` | A closed form of Dive+: one global 3×3 matrix rebuilding red as a hue-shifted mix of all three channels, the angle chosen from the frame's mean red, then a 0.4/99.9 per-channel stretch. |
| `hue-shift-clarity` | `hue-shift`, then a texture-gated local-contrast pass on CIELAB **L** only — colour never moves, and flat open water gets none. |
| `hue-shift-clarity-near` | `hue-shift-clarity` with the clarity additionally gated by post-correction warmth (pooled b\*), so still-blue far regions and haze are left alone. |
| `ancuti-fusion` | Ancuti colour-balance-and-fusion: red compensation, gray-world white balance, then a multi-scale pyramid fusion of a sharpened and a gamma-corrected input. |
| `dicam` | The one learned method — the DICAM network, run at a capped working size with the correction transferred to native resolution. Needs the `[dicam]` extra and a one-off `underwater-color init`. |

The default menu is `hue-shift-clarity`, `hue-shift-clarity-near`,
`hue-shift`. **Order is precedence**: the first entry a photo actually has is
the one a consumer shows. There is deliberately no scorer and no per-photo
"best" — a fixed rule out-scored every scorer tried.

Only `channel-stretch` and `hue-shift` have a clip-wide closed form, so those
are the two available for video; the rest are photo-only.

## Usage

```python
import numpy as np
from PIL import Image
import underwater_color as uc

arr = np.asarray(Image.open("dive.jpg").convert("RGB"))
Image.fromarray(uc.hue_shift_clarity(arr)).save("dive.corrected.jpg")
```

Every generator is `uint8` RGB in, `uint8` RGB out, same shape.

For video, estimate the parameters once from sampled frames and bake them into
a single filter for the whole clip:

```python
from pathlib import Path

import numpy as np
import underwater_color as uc

src = Path("clip.mp4")
frames = uc.sample_frames(src, 12)
stacked = np.concatenate([f.reshape(-1, 3) for f in frames]).reshape(-1, 1, 3)
uc.transcode(src, Path("clip.corrected.mp4"),
             vfilter=uc.video_filter("hue-shift", stacked))
```

### Command line

    underwater-color dive.jpg clip.mp4 --variants hue-shift -o out/

Corrects the files named on the command line, writing `<stem>.<method><ext>`
beside each input (or under `-o DIR`). `--variants` is repeatable and defaults
to the menu above; `all` means every generator. `--force` overwrites existing
outputs and `--jobs N` sets the file-level parallelism. A video is skipped for
any method with no clip-wide form, rather than failing the run.

    underwater-color init

Downloads the sha256-pinned DICAM checkpoint into
`~/.cache/underwater-color/dicam/`. Only needed for the `dicam` method.
