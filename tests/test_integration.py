"""Integration tests for atlas-content-pipeline end-to-end flow."""
import json
import os
import tempfile
import unittest

sys_path = os.path.join(os.path.dirname(__file__), '..', 'scripts')
if sys_path not in os.path.dirname(os.path.dirname(__file__)):
    import sys
    sys.path.insert(0, sys_path)

from getnote_frontmatter_pipeline import (  # noqa: E402
    Note,
    parse_export,
    score_note_for_p0,
    select_notes,
    heuristic_frontmatter,
    validate_frontmatter,
)


class TestEndToEndHeuristic(unittest.TestCase):
    """Full pipeline test: parse -> score -> select -> frontmatter."""

    def test_full_pipeline_heuristic(self):
        markdown = """## 1. HSK1 基础词汇 {#note-1} | 标签: hsk1, 词汇 | 创建: 2024-01-15

你好世界

## 2. 商务会议用语 {#note-2} | 标签: 商务 | 创建: 2024-02-01

今天开会讨论项目

## 3. 日常问候 {#note-3} | 标签: 日常, 问候 | 创建: 2024-02-15

你好吗？吃了吗？
"""
        # Step 1: Parse
        notes = parse_export(markdown)
        self.assertEqual(len(notes), 3)

        # Step 2: Score
        scores = [(n, score_note_for_p0(n)) for n in notes]
        self.assertTrue(any(s > 0 for _, s in scores))

        # Step 3: Heuristic frontmatter for top scored note
        best_note = max(notes, key=lambda n: score_note_for_p0(n))
        fm = heuristic_frontmatter(best_note)
        errors = validate_frontmatter(fm)
        self.assertEqual(errors, [])
        self.assertIn('title', fm)
        self.assertIn('category', fm)
        self.assertIn('tags', fm)


class TestPipelineEdgeCases(unittest.TestCase):
    """Test edge cases in the pipeline."""

    def test_parse_note_with_empty_body(self):
        markdown = "## 1. Empty Note {#note-1} | 标签: test | 创建: 2024-01-01\n\n"
        notes = parse_export(markdown)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].body_markdown.strip(), '')

    def test_parse_note_with_special_characters(self):
        markdown = "## 1. 特殊字符: <>&\" {#note-1} | 标签: test | 创建: 2024-01-01\n\n内容"
        notes = parse_export(markdown)
        self.assertEqual(len(notes), 1)
        self.assertIn('特殊字符', notes[0].title)

    def test_score_note_with_empty_tags(self):
        note = Note(999, 'Random Note', None, [], '', '', '')
        score = score_note_for_p0(note)
        # Should not crash, score depends on content
        self.assertIsInstance(score, (int, float))


if __name__ == '__main__':
    unittest.main()
