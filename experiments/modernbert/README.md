# ModernBERT Intent Experiment

This folder is isolated from the production Momentum intent pipeline.

The goal is to test whether a newer encoder architecture can beat the current best local model for Momentum capture routing.

## Current Production Baseline

The current best model is:

```text
models/momentum_intent/premium_latest/
```

Baseline architecture:

```text
microsoft/MiniLM-L12-H384-uncased
```

Baseline result:

```text
Test accuracy: 98.30%
Test macro F1: 98.30%
Parameters: 33,361,540
Checkpoint size: about 133 MB
```

## First Full Result

Run:

```text
experiments/modernbert/runs/full_20260515_123012/
```

Latest copy:

```text
experiments/modernbert/latest/
```

Result:

```text
Base model: answerdotai/ModernBERT-base
Parameters: 149,607,940
Checkpoint size: about 598 MB
Training time: 936.1 seconds
Best epoch: 3
Validation macro F1: 98.50%
Test accuracy: 99.00%
Test macro F1: 99.00%
Personal correction macro F1: 99.85%
Hand-written realistic checks: 24 / 24 correct
```

ModernBERT is now the accuracy winner, but it is much larger than MiniLM.

Decision:

```text
Best accuracy: ModernBERT
Best production balance: MiniLM unless the larger model size is acceptable
```

## Experiment Question

Can ModernBERT improve intent understanding for:

- short productivity text
- engineering/software notes
- ambiguous task/goal/note/plan phrases
- personal job-search style phrases

without becoming too heavy for a local-first app?

## Why ModernBERT

ModernBERT is a newer BERT-style encoder architecture. It is still an encoder, not a chat generator.

That makes it a good fit for Momentum because our core problem is:

```text
short text -> task / goal / note / plan
```

not:

```text
prompt -> generated answer
```

## Dataset

Default dataset:

```text
training_data/final/momentum_intent_20k_balanced.jsonl
```

Label balance:

```text
task: 5,000
goal: 5,000
note: 5,000
plan: 5,000
```

## Recommended First Experiment

This experiment needs a Transformers version that recognizes `model_type=modernbert`.
On this machine, the working stack is:

```text
transformers 5.8.1
tokenizers 0.22.2
accelerate 1.13.0
```

Use the small ModernBERT variant first:

```powershell
py -3.11 experiments/modernbert/train_modernbert_intent.py `
  --device cuda `
  --base-model answerdotai/ModernBERT-base `
  --epochs 4 `
  --batch-size 16 `
  --eval-batch-size 32 `
  --max-length 48
```

If memory is tight, reduce:

```powershell
--batch-size 8 --eval-batch-size 16
```

## Output

Experiment runs are saved under:

```text
experiments/modernbert/runs/
```

The latest successful experiment is copied to:

```text
experiments/modernbert/latest/
```

## Success Criteria

ModernBERT should replace MiniLM only if it gives a meaningful improvement.

Recommended decision rule:

```text
Use ModernBERT if:
  macro F1 improves by at least 0.5 percentage points
  and CPU inference is still acceptable
  and model size is acceptable

Otherwise:
  keep MiniLM as production model
```

The first full run improves test macro F1 by about 0.70 percentage points:

```text
MiniLM:     98.30%
ModernBERT: 99.00%
```

That is a real improvement, but the model is about 4.5x larger by parameter count and about 4.5x larger on disk.

## Why This Is Separate

The MiniLM pipeline already works well. ModernBERT is a challenger experiment.

Keeping it separate lets us compare architectures cleanly:

```text
production model: models/momentum_intent/premium_latest/
experiment model: experiments/modernbert/latest/
```

## Test A Trained Experiment

```powershell
py -3.11 experiments/modernbert/predict_modernbert_intent.py "apply to capgemini tonight" --device cuda
py -3.11 experiments/modernbert/predict_modernbert_intent.py "linkedin every day" --device cuda
py -3.11 experiments/modernbert/predict_modernbert_intent.py "capgemini interview felt rough" --device cuda
py -3.11 experiments/modernbert/predict_modernbert_intent.py "job search roadmap" --device cuda
```

Expected labels:

```text
task
goal
note
plan
```
