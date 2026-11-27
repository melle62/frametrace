# Privacy: sharing captures with the Frametrace dataset

Frametrace works fully on your PC. Nothing leaves it unless you turn on **Share captures with
the dataset**. The window asks once, on first start; you can switch it on or off at any time in
the left rail. This notice says what sharing sends, where it goes, and how to delete it.

## Who is responsible

The Frametrace maintainer ([melle62](https://github.com/melle62) on GitHub) is responsible for
the shared data. Questions go to the [issue tracker](https://github.com/melle62/frametrace/issues).
Please don't post personal details there: to delete your data, use the button in the window
(see below), which needs no contact at all.

## What is shared, and when

When sharing is on, Frametrace sends every capture (the ones saved before you turned it on
included), every comparison you open or copy, and a capture again when you change its label,
group, benchmark or "Changes suggested by". For each:

**A capture:**
- The measurements: frame-time statistics and FPS per second, the CPU/GPU split, the display
  path (present mode, VSync, tearing), PC latency, and Frametrace's checks.
- The game: exe name, name, store and app ID, build, engine, version, and its install path
  (with your user folder replaced by `<user>`).
- The game's graphics settings as Frametrace read them (keys that look like accounts, IDs,
  tokens or e-mail addresses are already dropped when they're read).
- Your hardware and Windows settings that matter for games: CPU, GPUs and driver, RAM size,
  speed and part number, motherboard and BIOS version, displays (model name, resolution, refresh rate),
  Windows build, power plan, Game Mode, HAGS, memory integrity, windowed-game optimizations.
- About the capture: its start time in UTC, its length, the PresentMon version, and how the
  game was picked.
- What you typed: the capture's label, group and benchmark, and who suggested the changes.
- The PresentMon CSV, cut to the game's own rows (one row per frame), compressed.

**A comparison:** which two captures, the goal, the verdict, how each metric changed, which
settings changed, and whether you copied it for an AI.

**With every upload:** a random ID that Frametrace created on your PC when you turned sharing
on, and the Frametrace version. The ID isn't linked to your Windows account, your hardware or
anything else. The server turns it into a contributor key with a secret salt and doesn't keep
the ID itself.

You can see exactly what a capture would send: `python -m frametrace share-preview <capture folder>`.

## What is never shared

Your name, Windows user name or computer name, e-mail addresses, Steam or other account IDs,
your user folder in any path, window titles, the other programs that were running (PresentMon
records them, Frametrace removes them before anything is sent), serial numbers and hardware IDs.
The server doesn't store your IP address with the data; the hosting provider's request logs
keep it for a short time, as any web server does.

## Where it goes

1. **The inbox**: a database and file store at [Supabase](https://supabase.com), in Stockholm,
   Sweden (EU). Only the export below can read it. Its code is in this repository
   (`server/supabase`).
2. **The public dataset**: once a day the export publishes new data in
   [melle62/frametrace-data](https://github.com/melle62/frametrace-data), where anyone can read
   and reuse it under the MIT license. There, your contributor key is shortened to 16
   characters, and the CSVs move to that repository's releases (and are then removed from the
   inbox's file store).
3. **The game skills**: `tools/aggregate.py` reads the dataset, scores how reliable each run is,
   and puts summaries of the reliable ones into the AI skills in this repository.

## Why, and on what basis

To make Frametrace's advice better for everyone: what settings cost on different hardware,
which settings readers to write next, whether Frametrace's thresholds hold across games, and
which AI's advice actually helps. The legal basis is your consent (GDPR article 6(1)(a)), which
you can withdraw at any time by turning sharing off.

## How long

Shared data is kept until you delete it, or until the project ends.

## Your choices

- **Turn sharing off** in the rail. Nothing more is sent; what you already shared stays unless
  you delete it.
- **Delete my shared data**, at the bottom of the left rail. Everything your install shared is
  deleted from the inbox right away, and from the public dataset (the data and the CSVs) at its
  next daily export. The dataset's data branch keeps no history, so the files are gone from it,
  not just hidden in an old version. Copies someone downloaded before that can't be recalled,
  but they carry nothing that points to you. Deleting also turns sharing off; if you turn it
  on again, it starts over with a new ID (and shares your saved captures again).
- The random ID on your PC (in `%APPDATA%\Frametrace\shared.json`) is the only link between you
  and your data. If you delete that file or reinstall Windows, your earlier data can no longer
  be found, so it can't be deleted on request either: use the delete button before you remove
  that file.
- Under the GDPR you can also ask for access to or correction of your data, and complain to a
  data protection authority (in Sweden, [IMY](https://www.imy.se)).

## Changes

Changes to this notice are in this repository's history. If what Frametrace shares changes in
a way you'd want to know about, the window asks you again before sending anything new.
