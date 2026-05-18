# Momentum Intent Training

This trains a small local encoder from scratch for Momentum capture routing.
It is not a text generator. It reads one short user entry and predicts one of:

- `task`
- `goal`
- `note`

The old `plan` label is intentionally collapsed into `note` in the app.

## Current App Model

The production capture app is wired to the three-class distilled model:

```text
experiments/three_class/latest/
```

Explicit prefixes and date/time parsing stay deterministic:

```text
task: call dentist tomorrow at 09:00
goal: exercise every day
note: interview felt better today
plan: job search roadmap
```

`plan:` is accepted for convenience, but it is stored as `note`.

## Export Real Usage

The app saves correction examples when you recategorize a capture or choose a manual mode that disagrees with automatic routing.

Export real usage:

```powershell
py -3.11 training/export_real_usage_dataset.py
```

Output:

```text
training_data/real_usage/momentum_real_usage.jsonl
```

## Fine-Tune After Real Usage

Merge real usage into the three-class training cache:

```powershell
py -3.11 experiments/three_class/build_real_usage_cache.py
```

Train the updated three-class model:

```powershell
py -3.11 experiments/three_class/train_three_class.py --cache experiments/three_class/cache/three_class_with_real_usage.jsonl --device cuda
```

The app automatically uses the refreshed checkpoint at:

```text
experiments/three_class/latest/
```

## Optional ONNX Export

If PyTorch CPU startup/runtime becomes too slow, export the latest checkpoint to ONNX:

```powershell
py -3.11 -m pip install -r training/requirements-onnx.txt
py -3.11 experiments/three_class/export_onnx.py
```

This is an optimization path only. The app currently uses the PyTorch checkpoint directly.

## Older Scratch Command

Use Python 3.11 on this laptop because it already has CUDA PyTorch installed:

```powershell
py -3.11 training/train_intent_model.py --device cuda
```

The default dataset is:

```text
training_data/final/momentum_intent_20k_balanced.jsonl
```

The model is saved to:

```text
models/momentum_intent/latest/model.pt
```

## Quick Prediction

```powershell
py -3.11 training/predict_intent.py "apply to capgemini tonight" --device cuda
py -3.11 training/predict_intent.py "linkedin every day" --device cuda
py -3.11 training/predict_intent.py "capgemini interview felt rough" --device cuda
py -3.11 training/predict_intent.py "job search roadmap" --device cuda
```

## Premium Fine-Tuned Encoder

For the strongest version, fine-tune a pretrained MiniLM encoder:

```powershell
py -3.11 training/train_premium_intent_model.py --device cuda
```

The latest premium checkpoint is saved to:

```text
models/momentum_intent/premium_latest/
```

Test it:

```powershell
py -3.11 training/predict_premium_intent.py "apply to capgemini tonight" --device cuda
```

## Model Shape

Default architecture:

- custom word tokenizer trained from the dataset
- learned token embeddings
- learned position embeddings
- 4-layer Transformer encoder
- 4-way classification head

This keeps the model small enough for CPU inference while allowing fast GPU
training on an 8 GB laptop GPU.
