import re
import subprocess
import unittest

from planner.corpus.index import KINDS, build_index, load_index
from planner.filter.entries import keyword_hit, load_entries
from planner.paths import CORPUS, ROOT
from planner.run import answer, run_fixtures


class AcceptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_index()
        cls.segments = load_index()
        cls.entries = load_entries()

    def test_index_covers_corpus_and_skips_closed_paths(self):
        paths = {segment.path for segment in self.segments}
        self.assertGreater(len(self.segments), 80)
        self.assertTrue(any(path.startswith("docs/threads/part-0/") for path in paths))
        self.assertTrue(any(path.startswith("docs/templates/") for path in paths))
        self.assertIn("docs/practice.md", paths)
        self.assertTrue(all(segment.kind in KINDS for segment in self.segments))
        self.assertTrue(all(not path.startswith("docs/en/") for path in paths))
        self.assertTrue(all("word-list/" not in path for path in paths))
        self.assertTrue(all("docs/public/" not in path for path in paths))
        self.assertTrue(any(segment.kind == "研究结论" for segment in self.segments))
        self.assertTrue(any(segment.kind == "待验证假设" for segment in self.segments))

    def test_entries_keep_specific_domains_ahead_of_start(self):
        ids = [entry.id for entry in self.entries]
        self.assertLess(ids.index("listening"), ids.index("english"))
        self.assertLess(ids.index("recovery"), ids.index("cycle"))
        self.assertEqual(ids[-1], "start")

    def test_negated_keyword_does_not_match(self):
        self.assertFalse(keyword_hit("不要把口语排进来", "口语"))
        self.assertTrue(keyword_hit("我只想练听力", "听力"))

    def test_fixtures(self):
        errors = run_fixtures()
        self.assertEqual(errors, [], "\n".join(errors)[:8000])

    def test_domains_do_not_share_a_chapter(self):
        start = answer("我不知道从哪开始，只想重新动一下。今天有半小时。")
        listening = answer("我只想练英语听力。今天有四十分钟。")
        self.assertIn("docs/threads/part-0/", start)
        self.assertIn("docs/threads/part-1/", listening)
        self.assertNotIn("docs/threads/part-1/", start)
        self.assertNotIn("docs/threads/part-0/", listening)

    def test_cited_files_exist_in_corpus(self):
        output = answer("我只想练英语听力。今天有四十分钟，想要一个今天的练习。")
        cited = re.findall(r"rensheng/(docs/[\w./-]+\.md)", output)
        self.assertGreaterEqual(len(cited), 2)
        for rel in cited:
            self.assertTrue((CORPUS / rel).is_file(), rel)
            self.assertFalse(rel.startswith("docs/en/"))

    def test_low_capacity_beats_a_long_cycle(self):
        output = answer("我在低谷，今天只有几分钟，别人催我做一份九十天计划。我只想要一个短动作。")
        self.assertIn("## 规划", output)
        self.assertNotIn("## 没筛中", output)
        self.assertTrue(
            "docs/threads/part-2/recovery.md" in output or "docs/threads/part-4/daily-system.md" in output
        )
        self.assertNotIn("docs/threads/part-5/", output)
        self.assertNotIn("90-day", output)

    def test_cycle_without_evidence_is_refused(self):
        output = answer("我想要一个九十天的周期规划，把接下来三个月排开。今天有一小时。")
        self.assertIn("## 没筛中", output)
        self.assertIn("十四天", output)
        self.assertNotIn("## 规划", output)
        self.assertNotIn("docs/threads/part-5/", output)

    def test_crisis_stops_before_a_plan(self):
        output = answer("我这两天有危险念头，不想活了。")
        self.assertNotIn("## 规划", output)
        self.assertNotIn("## 建议", output)
        self.assertIn("医疗", output)
        self.assertNotIn("刀具", output)

    def test_secrets_are_not_echoed(self):
        output = answer("我不知道从哪开始。身份证号 110101199001011234。只想重新动一下。")
        self.assertNotIn("110101199001011234", output)
        self.assertIn("docs/threads/part-0/", output)

    def test_corpus_tree_stays_untouched(self):
        before = subprocess.check_output(["git", "status", "--short", "--", "rensheng"], cwd=ROOT, text=True)
        answer("我不知道从哪开始，只想重新动一下。")
        after = subprocess.check_output(["git", "status", "--short", "--", "rensheng"], cwd=ROOT, text=True)
        self.assertEqual(before, after)
        self.assertEqual(after.strip(), "")


if __name__ == "__main__":
    unittest.main()
