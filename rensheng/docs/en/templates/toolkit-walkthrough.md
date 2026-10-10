---
title: "Toolkit Walkthrough: Let AI Continue a 90-Day Learning Project across Sessions"
description: Use an explicitly synthetic Python-learning case to show how Learning State, an AI Task Brief, an unaided baseline, an artifact, an Evidence Chain, Weekly Review, and a Reader Field Note hand work over.
updated: 2026-09-02
---

# Toolkit Walkthrough: Let AI Continue a 90-Day Learning Project across Sessions

Many readers do not lack plans. They do not know when each worksheet should open. Another common problem appears during a three-month learning project: one AI conversation grows too long, while a new conversation seems to erase the state that came before it.

The answer is not to demand permanent memory from AI. **Let a file preserve state and let AI handle the current task.**

This page uses a Python learner preparing for a career change as a complete walkthrough. The person, tasks, code results, scores, and feedback are synthetic. They demonstrate how to fill the tools; they are not a real reader outcome and do not prove that ninety days is enough for a career transition.

## This Is Not a Success Story

The demonstration learner has these conditions:

- Can read variables, conditions, and simple loops but cannot independently complete a small program;
- Can reliably invest four 45-minute sessions each week;
- Has a ninety-day goal of independently completing a command-line tool that reads CSV, validates rows, and prints a summary;
- Will not upload company data, ask AI to write the final artifact, or repay interruption with lost sleep;
- Will not add frameworks or another course if core code still cannot be explained on day fourteen.

These conditions are demonstration boundaries. Your starting point, time, body, work, and goal may differ completely.

## Scene: Why the Plan Loses Its Memory

The initial failure is to leave everything inside one chat window:

1. Ask AI for a twelve-week plan;
2. Ask questions, practise, and revise code in the same conversation every day;
3. Depend on prior messages to preserve errors, progress, and the next step;
4. As context grows, new answers begin mixing old tasks together;
5. After opening a new conversation, reconstruct the learner from a long recollection.

Context length is not the only problem. A chat log has no stable version and does not clearly separate completed fact, AI interpretation, and next hypothesis. Learning state should not be trapped inside one provider or one conversation.

## The Job of Each of Five Tools

| Tool | Job in this case | What it does not own |
| --- | --- | --- |
| [Learning State](learning-state.md) | Preserve cross-session facts, evidence, errors, boundaries, and next task | Every line of conversation |
| [AI Task Brief](ai-task-brief.md) | Bound the current 45-minute task, input, assistance, and acceptance | The whole life plan |
| [Evidence Chain](evidence-chain.md) | Compare unaided baseline, assisted version, delayed retest, and transfer | Proving “mastery” through one score |
| [Weekly Review](weekly-review.md) | Change one variable from one week's evidence | Turning one poor week into a verdict about character |
| [Reader Field Note](reader-field-note.md) | Record whether the toolkit entered action and where it remained unusable | Public disclosure or a rating of the book |

If this is your first use of the toolkit, follow this page for one week. Do not open every other template at the same time.

## Step One: Put State outside the Conversation

The learner creates `python-learning-state.md` instead of using an AI thread as memory:

```markdown
# Learning State — python-90d-v1

Updated: 2026-09-02
Ninety-day situation: independently deliver a CSV-summary command-line tool and explain input validation, error handling, and tests.
Current baseline: can write variables, if, and for; cannot independently read CSV, separate functions, or write tests.
Reliable capacity: Monday, Wednesday, Friday, and Sunday, 45 minutes each.
Existing evidence: baseline/day-01.py; crashes on a row with an empty value.
Repeated errors: looking at answers first; treating running code as explained code; changing several variables and losing the cause.
Boundaries: synthetic data only; submit my version first; no make-up study after 23:00.
Current phase: days 1–14, calibrate.
Smallest next task: read a 12-row synthetic CSV, skip empty rows, and print valid-row count plus total amount.
Acceptance: the unaided version runs; I can explain each function; at least one failing test is preserved.
Stop condition: save state when 45 minutes ends; do not stay up to finish.
```

The state file keeps only what can change the next action. Course notes, full chat logs, and every attempt belong in the evidence folder rather than on the state page.

## Step Two: Give AI One Task at a Time

A new conversation does not ask AI to “remember me”. It receives the latest state and one task brief:

```markdown
Below is my Learning State file. First restate the version, goal, current evidence, main errors, boundaries, and next task in no more than six bullets. Point out conflicts or gaps. Do not add facts that are absent.

This session has one task: read a synthetic CSV, skip empty rows, and print valid-row count plus total amount.
Process: let me submit an unaided version first; identify at most three problems that affect the result without giving full code; after I revise it, test with two cases. At 45 minutes, return five updates: completed, evidence, error/risk, handover, and next step.
```

AI's first job is to restate the state, not begin a lecture. When the restatement is wrong, repair the state or prompt before generating another plan on a false premise.

## Step Three: Save a Baseline before Asking for Help

The synthetic unaided attempt produces:

| Condition | Result | Evidence |
| --- | --- | --- |
| 25 minutes, no answer | Reads valid rows; empty amount raises an exception; all logic in one function | `evidence/week-01/baseline.py` |
| AI identifies only three issues | Empty-value validation, function ownership, and missing tests become visible | `evidence/week-01/feedback.md` |
| After revision | Normal-row and empty-row tests pass; invalid amount format remains unsupported | `evidence/week-01/revision.py` |

The record is not “AI wrote the program”. It says the unaided version exposed three issues, AI helped classify them, the learner repaired two, and the third became the next task.

Asking for complete code first may produce a better-looking file while erasing the baseline and any way to tell which ability belongs to the learner.

## Step Four: Put the Artifact into an Evidence Chain

Week one does not preserve the statement “learned CSV”. It records four time points:

| Time point | Condition | Synthetic result | What it still cannot show |
| --- | --- | --- | --- |
| Baseline | No AI, 25 minutes | 1/3 acceptance conditions pass | Understanding of error handling |
| Immediate after assistance | Three feedback points seen | 2/3 pass; two functions can be explained | Retention after several days |
| Day-seven delayed retest | Old code closed; parallel CSV | 2/3 pass; invalid amount is missed again | Adaptation to a new field |
| Transfer | Add a `currency` field | Finds where change belongs; currency validation incomplete | Structure begins to transfer, prerequisites remain missing |

The result is not perfect and is more informative than “maintained a seven-day streak”. The next variable is not pandas, a web framework, and a database. It is input validation and failing tests.

## Step Five: Continue in a New Conversation

The weekly review writes only decision-changing information back into state:

```markdown
# Learning State — python-90d-v2

Updated: 2026-09-08
Completed: normal and empty CSV rows; logic separated into read_rows and summarize.
Evidence: week-01/baseline.py; revision.py; day-07-retest.py; tests.md.
Delayed result: 2/3 conditions remain on day seven; invalid amount fails again.
Main error: failure paths lack tests; normal output causes testing to stop too early.
Boundaries retained: synthetic data; unaided answer first; stop at 45 minutes; no repayment of missed time.
Smallest next task: write three failing tests before implementing parse_amount.
Acceptance: empty, alphabetic, and negative inputs have explicit outcomes; design choice can be explained aloud.
Next review: 2026-09-15.
```

The old conversation can close. The new one needs only `v2` and the relevant evidence locations, not tens of thousands of words from the chat. **AI did not track learning across sessions. The state file tracked it, and AI read and served that state.**

## Step Six: Complete a Reader Field Note after Seven Days

The synthetic demonstration must also inspect whether the toolkit supported action:

```markdown
Entry problem: I did not know how a new AI conversation could continue a three-month plan.
Action: created a versioned Learning State, completed one CSV task, and saved an unaided version plus retest.
What remained after seven days: could write state v2 without the old chat and begin one defined task in a new conversation.
Failed transfer: knew errors should be preserved but still did not know how to classify them.
Most useful: the five-tool responsibility table and filled state example.
Still abstract: phase gates need examples for more kinds of goals.
Cannot conclude: this workflow guarantees job readiness after ninety days.
```

The note remains private first. Only after paths, identity, and sensitive details are removed should a public version be considered.

## If the Week Is Interrupted

The state file does not require repayment of the whole plan. The first return record states facts:

```markdown
Interruption fact: no practice for seven days.
Cause evidence: two overtime evenings, one period of illness, no retest completed.
What I will not do: compress four lessons into the weekend or repay them through lost sleep.
Return action: run the previous tests, write one failing case, and update state.
24-hour acceptance: preserve the failing test and the next 25-minute entry point.
```

When health, safety, work responsibility, or relationships need priority, recovery itself can be the week's result. The plan serves life; life does not owe the plan an apology.

## Session Protocol You Can Copy

```markdown
1. Restate the submitted state version, goal, evidence, errors, boundaries, and next task.
2. Identify conflicts and missing information; do not infer unwritten history.
3. Handle one minimum task only and let me submit the unaided version first.
4. Give at most three high-impact feedback points, separating observation, interpretation, and suggestion.
5. Do not provide a complete answer unless I explicitly request it.
6. End with: completed, evidence, error/risk, handover, and next step.
7. Treat the file as the source of truth and do not claim memory of other conversations.
```

This protocol cannot guarantee that AI never errs. It makes errors easier to detect and preserves the learner's ownership of the problem, state, and final judgment.

## What This Walkthrough Shows and Does Not Show

It shows that five tools can form a clear handover: state lives outside the conversation, the task becomes smaller, unaided and assisted versions remain separate, a delayed retest occurs, and a new conversation has a reliable entry.

It does not show that:

- The synthetic learner will persist for ninety days;
- This task difficulty fits every beginner;
- AI always makes learning faster than studying without it;
- Completing a command-line tool equals real job readiness;
- One week represents long-term transfer.

In real use, preserve your own baseline, artifacts, time, cost, and failures. The example shows how to fill the records. Reality decides whether they are useful.

## Closing: Give Memory to the File and Keep Judgment with Yourself

A long learning project should not lose its past when a chat closes, and it should not impersonate continuity merely because one chat is long.

Let the state file remember what happened. Let evidence preserve what you actually made. Let the next conversation carry only the next step. Tools may change, models may update, and the plan may shrink. As long as you know where you came from, what remains unproved, and where the next task lives, learning is not trapped inside any conversation.

Related entry points: [Learning State](learning-state.md) | [AI Task Brief](ai-task-brief.md) | [Evidence Chain](evidence-chain.md) | [Reader Field Note](reader-field-note.md)
