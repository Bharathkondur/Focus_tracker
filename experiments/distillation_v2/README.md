# Distilled Student v2

This experiment tries to improve the small scratch-style model while keeping it much smaller than MiniLM and ModernBERT.

## Design

Student v2 uses:

- 10M-12M parameter Transformer encoder
- BPE tokenizer trained from Momentum text
- ModernBERT teacher probabilities
- MiniLM teacher probabilities
- extra hard ambiguous examples
- personal/correction examples
- early stopping

## Why V2

Student v1 result:

```text
Parameters: 6,337,284
Checkpoint size: about 25 MB
Test macro F1: 96.40%
Personal correction macro F1: 99.15%
```

V2 target:

```text
97% - 97.8% macro F1
```

## Step 1: Build Ensemble Teacher Cache

```powershell
py -3.11 experiments/distillation_v2/build_ensemble_cache.py --device cuda
```

This creates:

```text
experiments/distillation_v2/cache/ensemble_teacher_cache.jsonl
```

The cache contains:

- base training rows
- personal correction rows
- hard ambiguous rows
- ModernBERT teacher probabilities
- MiniLM teacher probabilities
- averaged ensemble probabilities

## Step 2: Train Student v2

```powershell
py -3.11 experiments/distillation_v2/train_student_v2.py --device cuda
```

Latest model:

```text
experiments/distillation_v2/latest/
```

## Prediction

```powershell
py -3.11 experiments/distillation_v2/predict_student_v2.py "apply to capgemini tonight" --device cuda
```

## Baselines

```text
Original scratch:    93.97% F1, about 12 MB
Distilled v1:        96.40% F1, about 25 MB
MiniLM fine-tune:    98.30% F1, about 133 MB
ModernBERT teacher:  99.00% F1, about 598 MB
```

## Results

Best run:

```text
experiments/distillation_v2/runs/student_v2_extra_20260515_150237/
```

Latest copy:

```text
experiments/distillation_v2/latest/
```

Configuration:

```text
Rows: 24,000
Sources: 20k base + 2k hard + 2k personal
BPE vocab: 8,174
Parameters: 10,030,724
Checkpoint size: about 39 MB
Best epoch: 28
```

Result:

```text
Validation macro F1: 97.13%
Test accuracy: 97.38%
Test macro F1: 97.37%
Personal correction macro F1: 99.60%
Manual realistic checks: 23 / 24 correct
```

Comparison:

```text
Original scratch:    93.97% F1, about 12 MB
Distilled v1:        96.40% F1, about 25 MB
Distilled v2:        97.37% F1, about 39 MB
MiniLM fine-tune:    98.30% F1, about 133 MB
ModernBERT teacher:  99.00% F1, about 598 MB
```

Decision:

```text
Distilled v2 is now the best small model.
MiniLM is still more accurate if 133 MB is acceptable.
ModernBERT remains the accuracy champion and teacher.
```

## Failed V2 Runs

The first v2 cache replaced hard/personal rows instead of oversampling them:

```text
Run: student_v2_20260515_144631
Test macro F1: 95.91%
```

A larger 11.65M version was also worse:

```text
Run: student_v2b_20260515_145626
Test macro F1: 95.26%
```

The improvement came from using the extra hard and personal examples as real extra rows.
