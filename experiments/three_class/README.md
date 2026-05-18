# Three-Class Momentum Intent Model

This experiment removes the `plan` class.

New labels:

```text
task
goal
note
```

Why:

```text
plan is ambiguous in real usage
plan competes with task and note
most strategy/roadmap/planning text is better stored as note/context
```

Mapping:

```text
task -> task
goal -> goal
note -> note
plan -> note
```

The app should still understand planning language, but it should save that text as a note unless the text has clear task signals like date, time, or action scheduling.

## Train

```powershell
py -3.11 experiments/three_class/build_cache.py
py -3.11 experiments/three_class/train_three_class.py --device cuda
```

Latest model:

```text
experiments/three_class/latest/
```
