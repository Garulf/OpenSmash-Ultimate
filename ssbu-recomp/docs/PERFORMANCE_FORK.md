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

The game counts the refreshes signalled by `display.c` as its time and draws
one picture per game step. No render pass exists that could draw a moment
between two steps. The possible routes, and why none was built in this pass:

- Frame generation after the game: a picture synthesized between two
  finished frames. The game gives no motion vectors, so this needs optical
  flow on the GPU. Each real frame waits for the next one, adding about one
  game frame (16.7 ms) of input latency, which matters in a fighting game.
  Particles, UI and text show the usual artifacts. External Vulkan layers
  already do this for any game; test against one before building it in.
  Building it in would also need a present path where the extra pictures do
  not count as refreshes for the game clock, plus a measured latency budget.
- Interpolating the game's own draws: replay frame N's commands with their
  constants blended toward frame N+1. This needs a match between the draws
  of two frames (the draw count changes from about 470 to 608 within one
  entrance) and knowledge of which constant bytes are matrices. Skinning,
  particles and UI would also have to stay consistent. Not attempted.
- A variable timestep in the game: the lifted code is the game's own fixed
  60 Hz logic. Changing it changes gameplay and the determinism that replays
  and rollback depend on.

### Even pacing on high-refresh monitors

A smaller problem is solvable: showing 60 FPS evenly. A 144 Hz panel cannot
show every 60 FPS frame for the same time; frames alternate between two and
three refreshes. The Windows build measures vblanks and, on a panel at k x 60
Hz (120, 240), locks its clock to every k-th vblank, so each frame stays on
screen for exactly k refreshes. The Linux build has no vblank source
(`vblank_thread` in `display.c`), so it always paces with its own 60.000 Hz
clock. That clock drifts against a 120 Hz panel too.

Two ways to fix this, neither implemented here:

- Variable refresh in the compositor (VRR, FreeSync or G-Sync Compatible): each
  present then starts a refresh, so the 60.000 Hz clock gives even frames.
  This is a compositor and monitor setting, not tested in this pass.
- A Linux vblank source for the existing display lock: DRM vblank events for
  the CRTC that shows the window, or Wayland presentation-time feedback. The
  hard part is mapping the SDL window's display to a DRM connector, which
  differs between X11, XWayland and Wayland.

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

## Read game code ahead

`SSBU_CODE_PREFETCH=1` (Linux) starts a background thread that reads the game
library into the page cache as the program starts, and each module as
`nn::ro` loads it. The game library holds 570 MB of lifted code, and every
fighter has a module of its own. Without the switch, code that first runs
during a match, such as a fighter's entrance, comes from the disk one page
fault at a time, on the game's main thread.

The thread runs at nice 10 and blocks the process's signals. It only reads
files and changes no game state or timing. It costs page cache for the files
it reads (about 600 MB in a four-player match), which the kernel can reclaim.
It is off by default. The thread reads the files instead of calling
`POSIX_FADV_WILLNEED`, because Linux reads no more than the device's
readahead window for that call (128 KB on the NVMe drive tested).

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
The next section identifies one cause of entrance stalls: game code that is
not yet in the page cache.

## Cold game code in entrances (2026-11-05)

Same machine, after a reboot. Four players (Palutena, Rosalina, Bayonetta,
Pikachu) on Final Destination at scale 2.0, with `SSBU_HITCH=20`. The game
ran in a 320x180 window on a private Xvfb display, because the desktop's
XWayland was hung at the time. Internal rendering stays 3840x2160, and a
four-Mario calibration run matched the earlier XWayland baseline.

Before each run the game library and modules were dropped from the page cache
(`POSIX_FADV_DONTNEED`), as after a reboot; the game data stayed cached. One
host binary was used, with the switch off and on in alternation, three runs
each:

| Per run | Off | On |
|---|---|---|
| Entrance frames over 20 ms (of 420) | 24, 21, 29 | 10, 14, 6 |
| Entrance 99th percentile, ms | 30.0, 31.4, 28.1 | 22.4, 22.4, 20.8 |
| Frames over 20 ms after the entrance | 19, 21, 25 | 10, 15, 16 |
| `SSBU_HITCH` frames over 20 ms, entrance on | 43, 41, 53 | 20, 29, 22 |
| Of those, main thread off a CPU in lifted code | 11, 14, 11 | 1, 2, 2 |
| Major page faults | 2,414, 2,413, 2,414 | 156, 156, 156 |

All six runs produced the same fight-state hash (4,484 records). With the
switch off, the main thread waited 5 to 6 ms at a time in page faults. A run
recorded with perf put most of those faults in the game library and the
fighter modules, with one burst of 42 ms. After the switch read the files, the whole
game library and all four fighter modules were cached, against 159 of 570 MB
and 19 of 26 MB without it.

The switch only matters while the code is not cached: the first matches after
a boot, or after memory pressure has evicted it. An earlier warm repeat
without the switch had 9 and 15 frames over 20 ms, close to the runs with it.

Not fixed by it: the first or second frame with fighters takes 38 to 50 ms in
every run, mostly in present and command submission. The other remaining
frames over 20 ms are mostly in the frame wait, a pacing effect that the
four-Mario warm baseline also shows (7 in its entrance).

With the switch on, a run under the Vulkan validation layer completed 2,283
frames, including the entrance, 300 fight frames and a normal shutdown,
without validation messages. The platform self-test (`tests/plat_selftest.c`)
passed with the switch off and on.

## Larger stalls in play

The watchdog's stall reports from play on the same machine show bigger gaps
than the benchmark runs. Their benchmarks shared a warm pipeline cache. In
one session, four gaps of 250 to 680 ms fell within five seconds around a
fight start:

- The first-run shader preparation had not run.
- Draws were held until their pipelines existed.
- The process used 3 to 9 s of CPU time in each gap, compiling on every core.

In a later session, after the preparation had finished (521 containers), no
such cluster appeared. Letting the first run's preparation finish keeps these
compiles out of matches. `shader_wait = skip` in `graphics.ini` leaves a draw
out near a fight instead of holding the frame, at the cost of missing
effects in those frames.

One gap of 2.7 s in that later session is not explained. Every thread was
idle, and the game's main thread waited on a system event. The Linux build
records no call stacks, so the report cannot say what it waited for.

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
