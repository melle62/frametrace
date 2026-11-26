# Frametrace skills

Frametrace's report is a complete prompt for any AI. These skills make the answers sharper: they
add game knowledge that was measured with Frametrace.

| Skill | For | Status |
|---|---|---|
| [`frametrace`](frametrace/SKILL.md) | any game without its own skill, and **game studies** that gather the data for a new one | general |
| [`frametrace-cs2`](frametrace-cs2/SKILL.md) | Counter-Strike 2 (`cs2.exe`, Steam app 730) | tested on one PC |

A game skill takes over from the general one for its game. Each skill is a single `SKILL.md` that
works on its own. Every Frametrace report ends its task with a `Skill:` line that names the skill
for the captured game (or the general one) and links its plain text, so an AI that can open links
can read it without installing anything.

## Using them
- **Claude:** add a skill's folder as a skill (zipped), or copy it into `~/.claude/skills/` for
  Claude Code. Add `frametrace` and the game skills you need.
- **Any other AI:** paste the game's `SKILL.md` (or `frametrace/SKILL.md`) as instructions, then
  paste the report.

## Adding a game
A game gets its own skill once it has been **studied**: its settings mapped, a repeatable scene
found, and its costs measured one change at a time. The general skill runs the study with you:

1. Paste a Frametrace report for the game and ask for a study ("study this game for a Frametrace
   skill"). The skill keeps a study log; paste it back to continue in a new session.
2. Follow its steps: settings inventory, a repeatable scene, two baseline runs that agree, the
   limit, then one-change captures.
3. When the log meets the readiness bar (step 7 in the skill), it drafts
   `skills/frametrace-<slug>/SKILL.md` from [`game-skill-template.md`](game-skill-template.md).
4. Run `python tools/sync_skills.py`, then `pytest`, and open a pull request with the study log.

Rules:
- One folder per game: `frametrace-<slug>/SKILL.md`. List it in the general skill's intro and in
  the table above.
- Measured numbers name the system, resolution, scene and runs. Guide claims say "guide" and
  link it. Everything else goes under "Not measured yet".
- Skills add knowledge. Frametrace and its reports must still work without them.
- No affiliate links or promotions.

## The shared rules
How to read a report, the per-goal rules, the answer format and comparisons are the same in every
skill. They live between the `frametrace:shared-rules` markers in
[`frametrace/SKILL.md`](frametrace/SKILL.md). Edit them there, then run:

```
python tools/sync_skills.py          # copy them into every game skill and the template
python tools/sync_skills.py --check  # what pytest checks
```

The same tool regenerates `frametrace/skill_index.py` (process name → game skill) from each game
skill's `metadata.process_names`: that's how the report's `Skill:` line knows the game has a skill.

## Community data
Each game skill (and the template) has a table between `frametrace:community-data` markers
under "Measured costs". It's generated from the shared
[Frametrace dataset](https://github.com/melle62/frametrace-data) by `tools/aggregate.py`:
one-change comparisons by trusted contributors only, each person's runs counted once, with
the GPUs and resolutions behind every row. Don't edit it by hand; a weekly workflow opens a
PR when it changes. How runs are judged: [docs/data.md](../docs/data.md).
