from __future__ import annotations

from datetime import date
import unittest

from momentum.capture.router import ContextRouter


class FakeMemory:
    def __init__(self) -> None:
        self.training_example_calls = 0

    def related(self, query: str, limit: int = 8):
        return []

    def training_version(self) -> tuple[int, int]:
        return (1, 1)

    def training_examples(self, limit: int = 300):
        self.training_example_calls += 1
        return [
            ("send resume", "task"),
            ("call recruiter", "task"),
            ("finish portfolio", "task"),
            ("apply tonight", "task"),
            ("exercise daily", "goal"),
            ("linkedin every day", "goal"),
            ("read every morning", "goal"),
            ("drink water daily", "goal"),
            ("felt tired", "note"),
            ("interview felt rough", "note"),
        ]


class FakeModel:
    status = "fake model"

    def warmup_async(self) -> None:
        return None

    def predict(self, text: str):
        return None


class RouterTests(unittest.TestCase):
    def test_tiny_classifier_is_cached_until_training_version_changes(self) -> None:
        memory = FakeMemory()
        router = ContextRouter(memory, local_model=FakeModel(), preload_model=False)
        base = date(2026, 5, 21)

        self.assertIsNotNone(router.route("random thought", base))
        self.assertIsNotNone(router.route("another random thought", base))

        self.assertEqual(memory.training_example_calls, 1)


if __name__ == "__main__":
    unittest.main()
