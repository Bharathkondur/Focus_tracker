# ModernBERT To Scratch Distillation

This experiment trains a small Momentum student model using ModernBERT as the teacher.

Goal:

```text
Keep the small scratch-model size, but transfer some of ModernBERT's accuracy.
```

## Teacher

Teacher model:

```text
experiments/modernbert/latest/
```

Teacher result:

```text
Test macro F1: 99.00%
Personal correction macro F1: 99.85%
Parameters: 149,607,940
Checkpoint size: about 598 MB
```

## Student

Student model:

```text
custom Transformer encoder
```

This is a stronger version of the scratch model. It uses the same app-native training code style, but learns from:

- hard labels from `momentum_intent_20k_balanced.jsonl`
- soft teacher probabilities from ModernBERT
- personal correction examples from `personal_corrections_2k.jsonl`

## Why Distillation

Hard labels say only:

```text
this text is a task
```

Soft teacher probabilities also tell the student about ambiguity:

```text
task: 0.82
goal: 0.12
note: 0.02
plan: 0.04
```

That helps the small model learn smoother boundaries between task, goal, note, and plan.

## Step 1: Build Teacher Cache

```powershell
py -3.11 experiments/distillation/build_teacher_cache.py --device cuda
```

Output:

```text
experiments/distillation/cache/teacher_modernbert_cache.jsonl
```

## Step 2: Train Student

```powershell
py -3.11 experiments/distillation/train_student.py --device cuda
```

Latest distilled student:

```text
experiments/distillation/latest/
```

## Decision Rule

Use the distilled student if it beats the original scratch model by a clear margin.

Current baselines:

```text
Scratch:     93.97% macro F1
MiniLM:      98.30% macro F1
ModernBERT:  99.00% macro F1
```

Target:

```text
Distilled student: 96%+ macro F1
```

That would make it a strong lightweight local model.

## First Result

Best run:

```text
experiments/distillation/runs/student_20260515_131727/
```

Latest copy:

```text
experiments/distillation/latest/
```

Result:

```text
Parameters: 6,337,284
Checkpoint size: about 25 MB
Best epoch: 20
Validation macro F1: 97.10%
Test accuracy: 96.40%
Test macro F1: 96.40%
Personal correction macro F1: 99.15%
Manual realistic checks: 23 / 24 correct
```

Comparison:

```text
Original scratch:    93.97% macro F1, about 12 MB
Distilled student:   96.40% macro F1, about 25 MB
MiniLM fine-tune:    98.30% macro F1, about 133 MB
ModernBERT teacher:  99.00% macro F1, about 598 MB
```

Decision:

```text
The distilled student is the best small model so far.
MiniLM is still the best production balance if 133 MB is acceptable.
ModernBERT remains the accuracy teacher/champion.
```

## Second Mix Tried

Run:

```text
experiments/distillation/runs/student_hard_20260515_132516/
```

Changes:

```text
hard_weight: 0.65
soft_weight: 0.35
temperature: 2.0
personal_weight: 1.5
```

Result:

```text
Test macro F1: 96.30%
```

This was slightly worse than the first run, so `latest/` points back to the first run.
