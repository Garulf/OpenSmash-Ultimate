# Linux performance experiments

This fork's Linux work targets the ssbu-recomp runtime in this directory and
game version 13.0.4. The repository root's WindowSmash runtime is a separate
implementation. No game binaries, generated game sources, assets or saves are
part of this fork.

## Higher frame rates

The current game clock advances simulation once per presented frame. Removing
its wait changes game speed. `SSBU_SPEED=0` already provides uncapped
fast-forward for benchmarks; `SSBU_SPEED=2` requests twice normal speed. These
are test modes, not normal-speed high-refresh rendering. Audio is wall-clock
driven; use `SSBU_AUDIO_MUTE=1` in fast-forward benchmarks.

Normal-speed rendering above 60 FPS needs a separate rendering clock and
interpolation, or a validated variable-timestep implementation. Neither is
implemented here. Increasing the refresh-event frequency alone is not a fix.

## Measure match entrances

The existing end-of-run fight report excludes the first 30 battle frames.
Particle-heavy entrances need those frames included. Set an absolute output
path before launching the game:

```sh
SSBU_VK_FRAMECSV="$PWD/frames.csv" ./play.sh
python3 scripts/linux/frame_report.py frames.csv --intro-frames 420
```

The CSV records the first 40,000 presented game frames. It includes time
between presents, GPU timestamp spans, render-thread batch replay, GPU fence
waits, pipeline work, draw counts, and skipped draws. The file is written during
normal shutdown, avoiding per-frame disk I/O. GPU timestamps are enabled by
this option when supported; an empty GPU field means no sample was available.
It records timings and counts, not game memory or images.

The `fighters` column uses the existing heuristic: a frame has compute
dispatches and more than 120 draws. The report's entrance window is the first
420 such frames (seven nominal seconds), including the first 30. This is not
a semantic detector for entrance animations. GPU time sums command-buffer
timestamp spans; it can include scheduling interference and is not a measure
of shader execution alone. Replay time can include waits, so do not add it to
the other timing columns as if they were independent.

For fair comparisons, keep the save snapshot, scripted inputs, fighter/stage
selection, scale, GPU, driver and cache state the same. Run variants
sequentially. Separate cold-cache behavior from repeat runs and repeat a
promising result before changing defaults. `SSBU_DETERMINISTIC=1`,
`SSBU_FIXED_SEED=1`, `SSBU_SEQ` and `SSBU_FIGHT_HASH` support comparisons; verify
the logs rather than assuming those switches guarantee equality.

## Build an alternative host runtime

`RECOMP_HOST_OPT=-O2` or `-O3` changes optimization of the host's C and C++
sources. The default stays `-O1`; the lifted game and fighter libraries keep
their existing settings. `-Ofast` is rejected. No fast-math or CPU-specific
instruction-set flags are added.

Use different `RECOMP_EXE` names for side-by-side host builds. The per-executable
object directory now records compiler and flags. Changing them rebuilds host
objects; an interrupted or failed change cannot silently reuse mixed flags.
This is a build experiment, not a demonstrated performance improvement.

## Existing renderer experiments

`SSBU_VK_VICACHE=1` enables this fork's vertex-input command cache. It compares
complete host binding and attribute descriptions, re-emits the state after
command-buffer resets or our own static-state pipeline, and still binds
vertex buffers and their current offsets for each draw. This avoids redundant
`vkCmdSetVertexInputEXT` calls, consistent with the command's
[dynamic-state semantics](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdSetVertexInputEXT.html).
It is opt-in and does not reduce particles or change simulation speed.

- `SSBU_VK_SPLIT=128` submits recorded commands at a pass boundary once at
  least 128 draws have accumulated. It can overlap CPU recording and GPU work,
  at the cost of extra submissions. Default: zero, unchanged.
- `SSBU_VK_CBMEM=0` requests CPU-cached host memory for compute buffers instead
  of the NVIDIA default's device-local preference. It can trade read-back cost
  for GPU access cost. Measure on the target hardware.
- `resolution_scale=2.0` renders screen-sized targets at 3840x2160.
  `1.333333` gives 2560x1440; `1.0` uses the original 1920x1080 path. A smaller
  scale can reduce GPU load, but does not by itself fix CPU stalls.

These options need before/after measurements. Defaults have not been changed
based on a single favorable frame or an average-FPS figure.

## First Albedo measurements (2026-11-05)

NixOS, Ryzen 7 5800XT, RTX 5080 through PRIME/XWayland, 13.0.4, four Mario
fighters on Final Destination, copied saves, scripted inputs, and warm caches:

- The vertex-input cache avoided 981,471 of 1,342,376 state commands in one
  uncapped test. Fight-state logs were identical between that comparison's
  baseline and cache runs (8,084 records). Captured images were close but not
  byte-identical; this is not a claim of pixel-exact equivalence.
- Uncapped fight throughput was 215.2 FPS without the cache and 214.4 with it.
  Those individual runs do not demonstrate an FPS improvement. Uncapped here
  means fast-forward, not normal-speed play at 214 FPS.
- Normal-speed runs stayed near 60 FPS but still contained entrance stalls.
  At scale 2.0, entrance GPU spans reached about 13 ms; scale 1.333333 reduced
  that maximum to about 9 ms in its run, without resolving all wall-time
  spikes. These are single-run observations, not general guarantees.
- Host `-O2`, earlier submission and cached compute-buffer memory did not
  establish a reliable entrance-frame improvement. Cached compute-buffer
  memory made this test's entrance GPU times worse, so it remains unchanged.
- Explicit Vulkan validation completed 2,216 frames including the entrance,
  fight and clean shutdown with no validation messages after fixing leaked
  read-back staging buffers. That leak fix is enabled normally.

The severe particle-related collapse reported by the player has not been
fully reproduced or fixed. The measurements and opt-in cache provide a
starting point; normal-speed high-refresh rendering remains unimplemented.
Steam Deck hardware, macOS and Windows gameplay were not tested in this pass.
