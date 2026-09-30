# dicam

The one learned method: the DICAM convolutional network, with its published
weights.

## What it does

The network processes each color channel separately with Inception-style
multi-scale convolution blocks, reweights their features with channel-wise
attention, then merges and reduces them back to RGB. It never downsamples,
so memory grows with image size. This library therefore:

1. shrinks the photo so its long side is at most 1024 px (`WORK_LONGEST`);
2. runs DICAM on that;
3. takes the per-pixel ratio of DICAM's output to its input, which is
   smooth, scales that ratio map back up to full resolution, and multiplies
   it into the original.

The result has DICAM's color with the original's full-resolution detail.

**On the web page** the network runs through onnxruntime-web at 512 px
instead of 1024, because the browser cannot allocate enough memory for
more. It differs from the library's output by about 1.4 levels on average
(7 at the 99th percentile).

## Source

H. Farhadi Tolie, J. Ren and E. Elyan, "DICAM: Deep Inception and
Channel-wise Attention Modules for underwater image enhancement,"
*Neurocomputing* 584:127585, 2024.
[doi:10.1016/j.neucom.2024.127585](https://doi.org/10.1016/j.neucom.2024.127585)

The network code is vendored, and the checkpoint downloaded, from the
authors' MIT-licensed repository,
[hfarhaditolie/DICAM](https://github.com/hfarhaditolie/DICAM) (commit
`c0dba84`). That checkpoint was trained on UIEB: C. Li et al., "An
Underwater Image Enhancement Benchmark Dataset and Beyond," *IEEE
Transactions on Image Processing* 29:4376–4389, 2020,
[doi:10.1109/TIP.2019.2955241](https://doi.org/10.1109/TIP.2019.2955241).

## Code

[`underwater_color/dicam.py`](../../underwater_color/dicam.py) and the
vendored network in
[`underwater_color/vendor/dicam/`](../../underwater_color/vendor/dicam/).
Needs the `[dicam]` extra and a one-off `underwater-color init`.
