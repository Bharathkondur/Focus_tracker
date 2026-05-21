from __future__ import annotations

from momentum.capture.classifier import TinyIntentClassifier, _features


def test_tiny_classifier_requires_enough_clean_examples() -> None:
    classifier = TinyIntentClassifier([
        ("send resume", "task"),
        ("", "goal"),
        ("not a real label", "plan"),
    ])

    assert not classifier.ready
    assert classifier.predict("send resume") == ("", 0.0)


def test_tiny_classifier_learns_repeated_phrase_patterns() -> None:
    examples = [
        ("send resume", "task"),
        ("email recruiter", "task"),
        ("finish portfolio", "task"),
        ("call hiring manager", "task"),
        ("exercise daily", "goal"),
        ("linkedin every day", "goal"),
        ("sleep routine", "goal"),
        ("read every morning", "goal"),
        ("interview felt rough", "note"),
        ("remember salary thought", "note"),
        ("journal mood", "note"),
        ("capgemini observation", "note"),
    ]
    classifier = TinyIntentClassifier(examples)

    assert classifier.ready
    kind, confidence = classifier.predict("email recruiter tomorrow")

    assert kind == "task"
    assert 0.0 < confidence <= 1.0


def test_features_normalize_words_prefixes_suffixes_and_bigrams() -> None:
    features = _features("  Email, recruiter!! today  ")

    assert features["w:email"] == 1
    assert features["p:emai"] == 1
    assert features["s:iter"] == 1
    assert features["b:email_recruiter"] == 1
