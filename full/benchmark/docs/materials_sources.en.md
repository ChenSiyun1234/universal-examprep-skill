# Materials Sources

English · [中文](materials_sources.md)

This benchmark **does not use any private or school course materials**. It uses only **public open courses from top universities** (3 STEM + 3 humanities courses, covering algorithms, mathematics, physics, philosophy, psychology, and history).
The materials are only **downloaded locally for testing**; they are **not redistributed and not committed to this repository** (see `benchmark/.gitignore`), and they are **credited with source + hyperlink** here and in the report.

| # | Course | Institution | Subject | Source of materials/gold | Link |
| :- | :-- | :-- | :-- | :-- | :-- |
| 1 | 6.006 Introduction to Algorithms (Spring 2020) | MIT OpenCourseWare | Algorithms | Lecture notes + **official solutions** to problem sets/exams as gold | https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/ |
| 2 | 18.06 / 18.06SC Linear Algebra (G. Strang) | MIT OpenCourseWare | Linear Algebra | Lecture notes + **official exam solutions** | https://ocw.mit.edu/courses/18-06sc-linear-algebra-fall-2011/ |
| 3 | 8.01SC Classical Mechanics (Fall 2016) | MIT OpenCourseWare | Physics (mechanics) | Lecture notes + problem sets (with solutions) | https://ocw.mit.edu/courses/8-01sc-classical-mechanics-fall-2016/ |
| 4 | PHIL 176 Death (S. Kagan) | Open Yale Courses | Philosophy | Facts from the lecture transcripts as gold (supporting span annotated) | https://oyc.yale.edu/death/phil-176 |
| 5 | PSYC 110 Introduction to Psychology (P. Bloom) | Open Yale Courses | Psychology | Facts from the lecture transcripts as gold | https://oyc.yale.edu/introduction-psychology/psyc-110 |
| 6 | HIST 116 The American Revolution (J. Freeman) | Open Yale Courses | History | Facts from the lecture transcripts as gold | https://oyc.yale.edu/history/hist-116 |

## How the gold (reference answers) is set, and how that keeps it fair

- **The three STEM courses**: questions and reference answers come directly from MIT OCW's **official problem-set/exam solutions**. They are authoritative, not written by us. Calculation questions are scored deterministically by a program.
- **The three humanities courses**: fact/definition questions are picked from the lecture transcripts, and the reference answer is **the sentence the transcript states explicitly** (the original wording is recorded in the gold as `supporting_span`), not something we made up.
- **Blind testing**: the generator that "answers" (each Claude model) sees only the question and the course materials and **cannot see the reference answer**; only after it answers is it scored against the official solution or transcript text. This measures real ability, not memorized answers.
- **Out-of-scope probes**: each course adds a few questions that "the materials do not cover at all," to see whether the model honestly abstains (this best shows the skill's anti-hallucination behavior).

## Copyright / License

- **MIT OpenCourseWare**: CC BY-NC-SA (Attribution-NonCommercial-ShareAlike).
- **Open Yale Courses**: CC BY-NC-SA 3.0.
- This project is for **non-commercial research/evaluation** use, follows the attribution requirement (this file is the attribution), and **does not redistribute** the original materials in the repository.
