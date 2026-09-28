# materials/ — Your Real Slides / Homework

English · [中文](README.md)

Student materials are **mixed and varied**, so use **one folder per course, with subfolders by type inside each course**. Don't pile everything together.

```
materials/
  ds/                        # course: Data Structures
    slides/                  #   lecture notes / PPT / PDF
      ch3_stack.pdf
      ch5_search.pdf
    homework/                #   homework (questions + your/official answers)
      hw2.pdf
    exams/                   #   past papers / sample papers / example_exam
      2025_final_sample.pdf
    notes/                   #   class notes / screenshots of the teacher's highlights
      key_points.png
  co/                        # course: Computer Organization
    slides/ ...
```

Agreed subtypes: `slides` (lecture notes), `homework` (homework), `exams` (sample/past papers), `notes` (notes/highlights).
Use what you have; if a type is missing, just leave it out. Take calculation questions from `homework` / `exams` where possible, so you can measure "calculation accuracy".

## Two ways to add them (pick one)

**A. Sort them yourself**: drag the files into the matching subfolders using the structure above. The least hassle and the most control.

**B. Dump everything into an inbox and let AI sort it** (for when you don't want to organize by hand):
1. First put all of this course's files into `materials/<课程>/_inbox/` (`<课程>` = course);
2. Send this in Claude Code:
   > "Please sort the files in `benchmark/materials/ds/_inbox/` by type: create `slides/ homework/ exams/ notes/` subfolders and move the files into them; leave anything you can't classify in `_inbox/` and give me a list."
3. The AI creates the folders and sorts the files automatically, and leaves anything it is unsure about for you to confirm.

## One more step: generate `_combined.txt` (needed by the baseline arm)

The baseline arm is "an ordinary AI without the skill", and the comparison is only fair if it gets **the same materials**. Combine the **plain text** of all the course's materials into one file:
> In Claude Code, say: "Convert all PDFs/PPTs/images under `benchmark/materials/ds/` **recursively** to plain text and merge them into `benchmark/materials/_combined.txt`."

(Test one course at a time; when you switch courses, just regenerate `_combined.txt`.)

## ⚠️ Privacy & copyright

When you run the tests, these materials are sent to Claude (in the cloud). **Don't include private information** (transcripts, ID cards…). Lecture notes are copyrighted by the teacher/school.
This directory is ignored in `.gitignore`, so it **will not be committed to the public repository**. Use it freely, but don't push it manually yourself either.
