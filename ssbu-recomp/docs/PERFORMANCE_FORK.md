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
  baseline and cache runs (8,084 records). One aligned frame capture matched
  an unchanged repeat baseline byte-for-byte. The first baseline capture had
  small pixel differences also present between the two unchanged baselines;
  this single capture does not establish equivalence for every frame.
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

## Source checks on NixOS

The five new source-only regression tests, all five existing compiler-scheduler
configurations, and the NEX self-test (25 tests) passed. The candidate host
runtime compiled with clang 21 and ran the real-game validation above.

The repository root's WindowSmash suite first ran on NixOS with 9 failures and
1 error. All were in the tests or their environment, plus one real tool bug:

- `tools/shader_aot.py`, `tools/arc.py` and `tools/nsz.py` on Python 3.10 to
  3.13 used zstandard's streaming decompressor, which returns whatever it has
  (often nothing) for a truncated frame. A broken compressed file looked empty.
  They now raise `ZstdError` unless the frame ended, as Python 3.14's
  `compression.zstd.decompress` does.
- `test_isa` and `test_fighter_sdk` ran clang-cl mode through Nix's cc-wrapper,
  which adds its Linux host's `-isystem`, `-fPIC` and hardening options to every
  command. The Windows probes now run the compiler named by clang's
  `InstalledDir`, which is the same clang outside Nix.
- `test_mac_installer`'s bootstrap tests set `PATH` to stand-ins and
  `/usr/bin:/bin`. On NixOS those two are envfs views of the looking process's
  `PATH`, so they held no `mkdir`, `tee` or `/bin/bash`. The tests now end that
  `PATH` with a folder of links to the tools the scripts use, after
  `/usr/bin:/bin`, so stand-ins keep priority and no other Python is found.
- `tools/linux/toolchain.py` takes clang, ld.lld, llvm-ar and llvm-nm from one
  folder. nixpkgs splits them over three packages, so importing it stopped the
  test. That is the documented contract, so the test shell provides the folder
  instead:

```nix
{ pkgs ? import <nixpkgs> { } }:
let
  python = pkgs.python313.withPackages (p: [
    p.pycryptodomex p.zstandard p.capstone p.unicorn p.pillow
  ]);
  llvmBin = pkgs.symlinkJoin {
    name = "windowsmash-llvm-bin";
    paths = with pkgs.llvmPackages; [ clang lld llvm ];
  };
in pkgs.mkShell { nativeBuildInputs = [ python llvmBin pkgs.pkg-config ]; }
```

With these, on NixOS 26.11 (clang 21.1.8, Python 3.13.16, envfs):
`python3 -m unittest discover -s tests` ran 1,156 tests, OK, 162 skipped.
Most skips need Windows or macOS; the others need numpy, a game dump, an
opt-in real multicast test, or git history (the test copy was an archive).
One earlier run also failed
`test_kernel_waits`: it was started as a zsh background job, and zsh's default
`BG_NICE` ran it at nice 5, the band those host-priority checks look for. Run
alone, after the earlier modules in one process, and in a full run started
with `setsid` at nice 0, it passed.
