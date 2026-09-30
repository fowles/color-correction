# Raw outputs and scripts

Everything here is a verbatim record: the tool output that each experiment's
numbers were read from, and the scripts that produced it. It is kept so a
number on an experiment page can be checked against what was actually
printed, not against a later summary.

## How it was recovered

The experiments were run in Claude Code sessions whose scratch directories
have since been deleted. The session transcripts survived. On 2026-09-30:

- **Outputs:** each `.txt` file is the text of one or more tool results from
  a transcript, found by a distinctive line of the output and de-duplicated.
  Each block is headed `##### <UTC timestamp>` of the result. Some outputs
  were read back from a file with line numbers, and keep them.
- **Scripts:** each script was rebuilt by replaying, in order, the file
  writes and edits recorded in the transcript (and, for `infer_knob.py`, the shell appends that followed). The version here is
  the last one written, which is the one whose output is kept, unless a page
  says otherwise.

**One change was made:** labelers' names are replaced with the same
pseudonyms used in [`../data/`](../data/) (`labeler-1` is the author). No
other byte was altered. Because they are verbatim, these files are exempt
from the repository's license-header rule, and are covered by its MIT
license like everything else.

## Re-running

The scripts document the analyses; most will not run as they are. They
import photogen modules of the time (some since deleted), read photos and
renditions from the photo library by absolute path, and write to scratch
directories. Only [`../analysis/approvals.py`](../analysis/approvals.py) is
maintained to run from this repository.

| directory | experiment |
| --- | --- |
| `03-hue-shift-fit/` | [03](../03-hue-shift-fit.md) |
| `04-scorer-and-removal/` | [04](../04-scorer-and-removal.md) |
| `05-label-round-2/` | [05](../05-label-round-2.md) |

Experiment 01 has no directory: its raw output was not kept anywhere.
Experiment 02 describes a protocol and has none.
