# skill_workspace/ — Run Directory for the Skill Arm

English · [中文](README.md)

This is the working directory for **the group with the skill installed** (the treatment) when it runs `claude -p`. It must be in the state
"skill active + file-locked knowledge base built", so that what gets tested is the skill's actual anti-hallucination mechanism.

## Setup (do this once per course before running the tests)

1. **Make the skill available in this directory**: put the skill in this directory's `.claude/skills/universal-exam-cram-coach/`
   (project level), or confirm it is installed in `~/.claude/skills/` (personal level, available everywhere).

2. **Use the skill to build the materials in `../materials/` into a knowledge base**: in this directory, use Claude Code to run the skill's initialization
   (the skill's first step: parse the syllabus → split with `ingest.py`), which produces:
   ```
   skill_workspace/
     references/
       wiki/ch1_*.md ...      # per-chapter knowledge slices
       quiz_bank.json          # fixed question bank (the answers are "locked" here)
     study_plan.md
     study_progress.md
   ```

3. **Confirm that `references/wiki/` and `references/quiz_bank.json` exist**. The skill arm relies on reading them when it answers
   ("read instead of re-deriving on the spot"), and that is exactly the mechanism under test.

> Note: build the knowledge base from the original materials in `../materials/`. **Do not** build it from the gold answers in `items/items.jsonl`;
> that would amount to "testing yourself with the answer key" and could not measure the real anti-hallucination effect. Write the gold set separately, independent of the skill's question bank.
