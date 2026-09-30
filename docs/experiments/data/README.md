# Data

## `variant-approvals.jsonl`

The approval-vote labels behind [the fixed menu](../05-label-round-2.md) and
[the removal of `gray-world` and `white-patch`](../04-scorer-and-removal.md):
350 records, one per labeled photo, collected with photogen's labeling server
between 2026-08-12 and 2026-08-17.

**Provenance.** A copy of `variant-approvals.jsonl` from the photo site
repository (`fowles/mfk-pics`, last written at its commit `4ad6cf4cd`,
sha256 of the original `7a07728569b2ccfdd3cc0e86b9948d608d980357beee29247beaf48f9854ad9a`).
The only change is that each labeler's name is replaced by a stable
pseudonym, in order of first appearance: `labeler-1` is the library's author,
`labeler-2` … `labeler-6` are five other volunteers. Every other byte of every
record is unchanged.

**Photos are not included.** `dive_slug` and `stem` identify the photo on the
public site; `images` pins the exact rendition each tile showed.

### Fields

| field | meaning |
| --- | --- |
| `dive_slug` | the dive the photo is from: `YYYY-MM-DD-<site>` |
| `stem` | the photo's content-derived id (16 hex digits) |
| `shown` | every tile on the labeling grid, `original` included |
| `approved` | the tiles the labeler approved; empty means every tile was rejected |
| `favorite` | the one tile the labeler starred, or `null` |
| `stratum` | `baseline`, `dark` or `noise-risk`, as defined in [the protocol](../02-labeling-protocol.md) |
| `context.metric` | the automatic scorer in use when the photo was labeled |
| `context.scores` | that scorer's score for each tile |
| `ts` | when the verdict was submitted (UTC) |
| `images` | per tile, a 7-hex-digit hash of the rendition that was shown |
| `labeler` | pseudonymous labeler id |
| `rotation` | the labeler's orientation fix in degrees (0/90/180/270), or `null`; present from 2026-08-12 |
| `cull` | `true` if the labeler proposed removing the photo; present from 2026-08-12 |

`rotation` and `cull` were collected for the photo site, not for color
correction, and no analysis here uses them.

Method names in `shown` and `approved` are this library's, plus three that
are not: `original` (the uncorrected photo), `dive-plus` (a correction
exported from the Dive+ phone app) and `google` (one from Google Photos).
The corrections labeled as `gray-world` and `white-patch` were the earlier
sRGB-encoded versions, not the linear-light ones this library now ships.

### Record

```json
{"dive_slug": "2025-10-06-lunkhead", "stem": "9ea946495b0f1450",
 "shown": ["ancuti-fusion", "channel-stretch", "dicam", "hue-shift", "hue-shift-clarity", "original"],
 "approved": ["hue-shift-clarity", "hue-shift"], "favorite": null, "stratum": "noise-risk",
 "context": {"metric": "contrast-nr", "scores": {"...": 0.0}}, "ts": "2026-08-17T01:28:48Z",
 "images": {"...": "..."}, "labeler": "labeler-6", "rotation": 0, "cull": null}
```

(`scores` and `images` abbreviated.)
