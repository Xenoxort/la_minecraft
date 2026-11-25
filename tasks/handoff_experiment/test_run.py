import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from run import evaluation_schedule, openai_headers, read_events, score, summarize, summarize_pairs, tasks, write_profiles


def inventory(time_ms, agent, has_target):
    return {"type": "inventory", "time_ms": time_ms, "agent": agent, "has_target": has_target}


class ScoreTests(unittest.TestCase):
    def test_single_holder_cannot_complete_both_objectives(self):
        result = score([inventory(1010, 0, True)], 1000, 5, 6000)
        self.assertEqual((result["status"], result["objectives"]), ("timeout", 1))

    def test_two_positive_snapshots_have_to_overlap(self):
        events = [inventory(1100, 0, True), inventory(1190, 1, True), inventory(1230, 0, False)]
        result = score(events, 1000, 5, 6000)
        self.assertEqual((result["status"], result["objectives"]), ("timeout", 1))

    def test_records_start_of_a_confirmed_joint_hold(self):
        events = [inventory(1100, 0, True), inventory(1400, 1, True)]
        result = score(events, 1000, 5, 1650)
        self.assertEqual((result["status"], result["completion_seconds"]), ("complete", .4))

    def test_late_inventory_event_cannot_complete(self):
        events = [inventory(1001, 0, True), inventory(6150, 1, True)]
        self.assertEqual(score(events, 1000, 5, 6500)["objectives"], 1)

    def test_disconnection_during_hold_is_an_error(self):
        events = [inventory(1100, 0, True), inventory(1200, 1, True),
                  {"type": "agent_exit", "time_ms": 1300}]
        self.assertEqual(score(events, 1000, 5, 1500)["status"], "error")


class DesignTests(unittest.TestCase):
    def test_schedule_pairs_conditions_on_each_scenario(self):
        suite = tasks()["held_out"]
        schedule = evaluation_schedule(suite, 5, 42)
        self.assertEqual(len(schedule), 30)
        self.assertEqual(schedule, evaluation_schedule(suite, 5, 42))
        for first, second in zip(schedule[::2], schedule[1::2]):
            self.assertEqual(first[:2], second[:2])
            self.assertEqual({first[2], second[2]}, {"baseline", "learned"})

    def test_report_keeps_errors_and_timeouts_distinct(self):
        planned = [("s", 1, "baseline"), ("s", 2, "baseline"), ("s", 3, "baseline")]
        rows = [{"scenario": "s", "arm": "baseline", "status": "timeout"},
                {"scenario": "s", "arm": "baseline", "status": "error"}]
        result = summarize(rows, planned)["s"]["baseline"]
        self.assertEqual((result["planned"], result["attempted"], result["timeout"], result["error"]),
                         (3, 2, 1, 1))
        self.assertEqual(result["completed_by_seconds"]["300"], 0)

    def test_treatment_only_adds_note_to_conversation_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            baseline = [json.loads(Path(p).read_text()) for p in write_profiles(folder, "model", "")]
            learned = [json.loads(Path(p).read_text()) for p in write_profiles(folder, "model", "Lesson.")]
            for control, treatment in zip(baseline, learned):
                self.assertEqual(treatment.pop("conversing"),
                                 control.pop("conversing") + "\nLessons from previous episodes:\nLesson.")
                self.assertEqual(control, treatment)

    def test_pair_summary_keeps_timeouts_and_excludes_errors_and_missing_runs(self):
        planned = [(scenario, rep, arm) for scenario, rep in (("s", 1), ("s", 2), ("s", 3), ("t", 1))
                   for arm in ("learned", "baseline")]
        outcomes = [
            ("s", 1, "baseline", "timeout", None), ("s", 1, "learned", "complete", 80),
            ("s", 2, "learned", "complete", 130), ("s", 2, "baseline", "complete", 110),
            ("s", 3, "baseline", "complete", 100), ("s", 3, "learned", "error", None),
            ("t", 1, "baseline", "timeout", None),
        ]
        rows = [dict(scenario=scenario, repetition=rep, arm=arm, status=status, completion_seconds=elapsed)
                for scenario, rep, arm, status, elapsed in outcomes]
        result = summarize_pairs(rows, planned)
        overall = result["overall"]
        self.assertEqual((overall["planned_pairs"], overall["valid_pairs"], overall["error"], overall["unpaired"]),
                         (4, 2, 1, 1))
        self.assertEqual((overall["both_complete"], overall["learned_only"], overall["baseline_only"]), (1, 1, 0))
        self.assertEqual(overall["learned_minus_baseline_completion_rate"], .5)
        self.assertEqual(overall["mean_learned_minus_baseline_capped_seconds"], -100)
        self.assertIsNone(result["scenarios"]["t"]["learned_minus_baseline_completion_rate"])

    def test_note_updater_uses_the_same_local_openai_configuration_as_the_bots(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "keys.json").write_text(json.dumps({"OPENAI_API_KEY": "file-key", "OPENAI_ORG_ID": "file-org"}))
            with patch("run.ROOT", root), patch.dict(os.environ, {
                "OPENAI_API_KEY": "environment-key", "OPENAI_ORG_ID": "environment-org",
                "OPENAI_PROJECT_ID": "environment-project",
            }, clear=True):
                self.assertEqual(openai_headers(), {
                    "Authorization": "Bearer file-key", "Content-Type": "application/json",
                    "OpenAI-Organization": "file-org", "OpenAI-Project": "environment-project",
                })

    def test_ignores_partially_written_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events.jsonl"
            path.write_text('{"type":"ready"}\n{"type":')
            self.assertEqual(read_events(path), [{"type": "ready"}])


if __name__ == "__main__":
    unittest.main()
