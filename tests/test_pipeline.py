#!/usr/bin/env python3
"""Unit tests for atlas-content-pipeline core functions."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import getnote_frontmatter_pipeline as pipeline
from getnote_frontmatter_pipeline import (  # noqa: E402
    Note,
    parse_export,
    score_note_for_p0,
    select_notes,
    slugify,
    ascii_slug_seed,
    validate_frontmatter,
    heuristic_frontmatter,
    detect_hsk_level,
    build_output_slug,
    format_frontmatter,
    CATEGORY_VALUES,
    AUDIENCE_VALUES,
    INTENT_VALUES,
    PILOT_VALUES,
)


class TestParseExport(unittest.TestCase):
    """Test the markdown export parser."""

    def test_parse_single_note(self):
        markdown = """## 1. 中文问候语 {#note-1} | 标签: 日常,问候 | 创建: 2024-01-15

你好世界
"""
        notes = parse_export(markdown)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].note_id, 1)
        self.assertEqual(notes[0].title, '中文问候语')
        self.assertEqual(notes[0].source_tags, ['日常', '问候'])

    def test_parse_multiple_notes(self):
        markdown = """## 1. 第一个笔记 {#note-1} | 标签: a | 创建: 2024-01-01

内容一

## 2. 第二个笔记 {#note-2} | 标签: b | 创建: 2024-01-02

内容二
"""
        notes = parse_export(markdown)
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0].note_id, 1)
        self.assertEqual(notes[1].note_id, 2)

    def test_parse_empty(self):
        notes = parse_export('')
        self.assertEqual(len(notes), 0)


class TestScoreNote(unittest.TestCase):
    """Test P0 scoring logic."""

    def test_hsk1_note_scores_high(self):
        note = Note(1, 'HSK1 基础词汇', '2024-01-01', ['hsk1', '词汇'], '', '', '')
        score = score_note_for_p0(note)
        self.assertGreaterEqual(score, 40)

    def test_ai_content_penalized(self):
        note = Note(200, 'AI产业深度解析', '2024-01-01', ['ai', '产业'], '', '', '')
        score = score_note_for_p0(note)
        self.assertLess(score, 0)

    def test_travel_content_scores(self):
        note = Note(5, '出行打车指南', '2024-01-01', ['旅行'], '', '', '')
        score = score_note_for_p0(note)
        self.assertGreater(score, 10)


class TestSlugify(unittest.TestCase):
    """Test URL slug generation."""

    def test_english_slug(self):
        self.assertEqual(slugify('Hello World'), 'hello-world')

    def test_chinese_slug_uses_replacements(self):
        result = slugify('中文课程')
        self.assertIn('chinese', result)

    def test_hsk_replacement(self):
        result = slugify('HSK1 基础')
        self.assertIn('hsk1', result)

    def test_empty_returns_fallback(self):
        result = slugify('!!!')
        self.assertTrue(len(result) > 0)


class TestAsciiSlugSeed(unittest.TestCase):
    """Test ASCII slug seed generation."""

    def test_chinese_mapping(self):
        self.assertEqual(ascii_slug_seed('中文'), 'chinese')
        self.assertEqual(ascii_slug_seed('拼音'), 'pinyin')
        self.assertEqual(ascii_slug_seed('时间表达'), 'time-expressions')


class TestValidateFrontmatter(unittest.TestCase):
    """Test frontmatter validation."""

    def test_valid_data(self):
        data = {
            'title': 'Test Title',
            'category': 'learn-chinese',
            'hsk_level': 1,
            'tags': ['tag-one', 'tag-two', 'tag-three'],
            'summary': 'A valid summary sentence that is long enough.',
            'audience': 'beginner',
            'intent': 'daily-life',
            'pilot_priority': 'p0',
        }
        errors = validate_frontmatter(data)
        self.assertEqual(errors, [])

    def test_missing_fields(self):
        errors = validate_frontmatter({})
        self.assertGreater(len(errors), 0)

    def test_invalid_category(self):
        data = {
            'title': 'Test',
            'category': 'invalid-category',
            'hsk_level': None,
            'tags': ['a', 'b', 'c'],
            'summary': 'A valid summary sentence that is long enough.',
            'audience': 'beginner',
            'intent': 'daily-life',
            'pilot_priority': 'p0',
        }
        errors = validate_frontmatter(data)
        self.assertTrue(any('category' in e for e in errors))

    def test_title_too_short(self):
        data = {
            'title': 'Ab',
            'category': 'learn-chinese',
            'hsk_level': None,
            'tags': ['a', 'b', 'c'],
            'summary': 'A valid summary sentence that is long enough.',
            'audience': 'beginner',
            'intent': 'daily-life',
            'pilot_priority': 'p0',
        }
        errors = validate_frontmatter(data)
        self.assertTrue(any('title' in e for e in errors))

    def test_tags_too_few(self):
        data = {
            'title': 'Test Title',
            'category': 'learn-chinese',
            'hsk_level': None,
            'tags': ['one'],
            'summary': 'A valid summary sentence that is long enough.',
            'audience': 'beginner',
            'intent': 'daily-life',
            'pilot_priority': 'p0',
        }
        errors = validate_frontmatter(data)
        self.assertTrue(any('tags' in e for e in errors))


class TestHeuristicFrontmatter(unittest.TestCase):
    """Test heuristic (no LLM) frontmatter generation."""

    def test_hsk_note_classification(self):
        note = Note(1, 'HSK1 基础词汇', '2024-01-01', ['hsk1'], '', '', '词汇表')
        fm = heuristic_frontmatter(note)
        self.assertEqual(fm['hsk_level'], 1)
        self.assertEqual(fm['category'], 'hsk-prep')
        self.assertEqual(fm['intent'], 'exam')

    def test_business_note_classification(self):
        note = Note(2, '商务会议用语', '2024-01-01', ['商务'], '', '', '会议内容')
        fm = heuristic_frontmatter(note)
        self.assertEqual(fm['category'], 'chinese-for-work')
        self.assertEqual(fm['intent'], 'business')

    def test_daily_life_classification(self):
        note = Note(3, '日常问候用语', '2024-01-01', ['日常'], '', '', '你好吗')
        fm = heuristic_frontmatter(note)
        self.assertEqual(fm['category'], 'learn-chinese')
        self.assertEqual(fm['intent'], 'daily-life')

    def test_valid_output(self):
        note = Note(4, '时间表达方式', '2024-01-01', ['时间表达'], '', '', '今天星期一')
        fm = heuristic_frontmatter(note)
        errors = validate_frontmatter(fm)
        self.assertEqual(errors, [])


class TestDetectHSK(unittest.TestCase):
    """Test HSK level detection."""

    def test_detect_hsk1(self):
        self.assertEqual(detect_hsk_level('HSK1 基础'), 1)
        self.assertEqual(detect_hsk_level('hsk 1'), 1)
        self.assertEqual(detect_hsk_level('HSK 一'), 1)

    def test_detect_hsk3(self):
        self.assertEqual(detect_hsk_level('HSK3 进阶'), 3)

    def test_no_hsk(self):
        self.assertIsNone(detect_hsk_level('中文学习'))


class TestSelectNotes(unittest.TestCase):
    """Test note selection logic."""

    def test_select_first(self):
        notes = [Note(i, f'Title {i}', None, [], '', '', '') for i in range(10)]
        import argparse
        args = argparse.Namespace(selection='first', limit=3, ids='')
        selected = select_notes(notes, args)
        self.assertEqual(len(selected), 3)

    def test_select_by_ids(self):
        notes = [Note(i, f'Title {i}', None, [], '', '', '') for i in range(10)]
        import argparse
        args = argparse.Namespace(selection='ids', limit=10, ids='1,3,5')
        selected = select_notes(notes, args)
        self.assertEqual(len(selected), 3)
        self.assertEqual({n.note_id for n in selected}, {1, 3, 5})


class TestBuildOutputSlug(unittest.TestCase):
    """Test output slug generation."""

    def test_slug_includes_note_id(self):
        data = {'title': 'Test Title'}
        note = Note(42, 'Test', None, [], '', '', '')
        slug = build_output_slug(data, note)
        self.assertIn('note-42', slug)


class TestFormatFrontmatter(unittest.TestCase):
    """Test YAML frontmatter formatting."""

    def test_frontmatter_format(self):
        data = {
            'title': 'Test Title',
            'category': 'learn-chinese',
            'hsk_level': 1,
            'tags': ['tag-one', 'tag-two'],
            'summary': 'Test summary.',
            'audience': 'beginner',
            'intent': 'daily-life',
            'pilot_priority': 'p0',
        }
        note = Note(5, 'Test', '2024-01-01', ['tag'], '', '', 'body')
        result = format_frontmatter(data, note, 'test-title--note-5')
        self.assertTrue(result.startswith('---'))
        self.assertIn('title: "Test Title"', result)
        self.assertIn('hsk_level: 1', result)
        self.assertIn('draft: true', result)


class TestValidationRegressions(unittest.TestCase):
    def setUp(self):
        self.note = pipeline.Note(1, '中文问候', None, [], '', '', '你好')
        self.valid = pipeline.heuristic_frontmatter(self.note)

    def test_non_object_is_rejected(self):
        for value in (None, [], 'title'):
            with self.subTest(value=value):
                self.assertTrue(pipeline.validate_frontmatter(value))

    def test_non_string_enums_are_rejected(self):
        for field in ('category', 'audience', 'intent', 'pilot_priority'):
            for value in ([], {}, None, 1):
                with self.subTest(field=field, value=value):
                    data = {**self.valid, field: value}
                    self.assertTrue(pipeline.validate_frontmatter(data))

    def test_invalid_tag_types_are_rejected(self):
        for value in (None, 123, {}, []):
            with self.subTest(value=value):
                data = {**self.valid, 'tags': ['valid', 'other', value]}
                self.assertTrue(pipeline.validate_frontmatter(data))

    def test_boolean_and_fractional_hsk_are_rejected(self):
        for value in (True, False, 1.5, '1'):
            with self.subTest(value=value):
                self.assertTrue(pipeline.validate_frontmatter(
                    {**self.valid, 'hsk_level': value}))

    def test_string_fields_round_trip_without_control_characters(self):
        value = 'A "quote" and C:\\notes\\unit\nnext\tline\r\x00'
        data = {**self.valid, 'title': value, 'tags': [value]}
        note = pipeline.Note(1, value, None, [value], '', '', '')
        rendered = pipeline.format_frontmatter(data, note, 'sample')
        for field in ('title', 'source_title'):
            line = next(line for line in rendered.splitlines()
                        if line.startswith(field + ': '))
            self.assertEqual(json.loads(line.split(': ', 1)[1]), value)
        for line in rendered.splitlines():
            if line.startswith('  - '):
                self.assertEqual(json.loads(line[4:]), value)


class TestPortableEntrypoints(unittest.TestCase):
    def test_missing_default_input_reports_one_line_error(self):
        script = Path(pipeline.__file__).resolve()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, str(script)], cwd=directory,
                env={'HOME': directory, 'PATH': os.defpath,
                     'PYTHONDONTWRITEBYTECODE': '1'},
                capture_output=True, text=True, timeout=10)
            self.assertFalse((Path(directory) / 'output').exists())
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertEqual(
            result.stderr,
            'Input file not found: input/getnote-export.md. '
            'Use --source to specify a GetNote export.\n')

    def test_defaults_are_portable(self):
        with patch.object(sys, 'argv', ['pipeline']):
            args = pipeline.parse_args()
        self.assertEqual(args.source, Path('input/getnote-export.md'))
        self.assertEqual(args.output_dir, Path('output/pilot'))

    def test_container_default_command_is_local_help(self):
        import subprocess
        dockerfile = Path(__file__).resolve().parents[1] / 'Dockerfile'
        directives = dict(line.split(' ', 1) for line in dockerfile.read_text().splitlines()
                          if line.startswith(('ENTRYPOINT ', 'CMD ')))
        command = json.loads(directives.get('ENTRYPOINT', '[]')) + json.loads(directives['CMD'])
        self.assertEqual(command[-1], '--help')
        self.assertEqual(command[1], 'scripts/getnote_frontmatter_pipeline.py')
        with tempfile.TemporaryDirectory() as home:
            result = subprocess.run([sys.executable, *command[1:]], cwd=dockerfile.parent,
                                    env={'HOME': home, 'PYTHONDONTWRITEBYTECODE': '1'},
                                    capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--source', result.stdout)


class TestDryRunRegressions(unittest.TestCase):
    def test_dry_run_does_not_resolve_provider_or_create_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.md'
            source.write_text('## 1. 中文问候 {#note-1}\n\n你好', encoding='utf-8')
            args = argparse.Namespace(source=source, output_dir=root / 'absent',
                                      provider='auto', selection='first', limit=1,
                                      ids='', dry_run=True)
            with patch.object(pipeline, 'parse_args', return_value=args), \
                    patch.object(pipeline, 'resolve_provider',
                                 side_effect=AssertionError('provider accessed')), \
                    patch('builtins.print'):
                self.assertEqual(pipeline.main(), 0)
            self.assertFalse(args.output_dir.exists())


class TestDeploySmokeCheck(unittest.TestCase):
    def run_smoke_check(self, mode):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            docker = root / 'docker'
            docker.write_text(f'#!{sys.executable}\n' + '''
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
command = args.pop(0)
pipeline = [sys.executable, os.environ['SMOKE_PIPELINE']]
if command == 'build' or command == 'stop':
    sys.exit(0)
if command == 'logs':
    os.execv(sys.executable, pipeline + ['--help'])
if command != 'run':
    sys.exit(64)
Path(os.environ['SMOKE_ARGS']).write_text(json.dumps(args))
if '-d' in args:
    print('smoke-container')
    sys.exit(0)
mode = os.environ['SMOKE_MODE']
if mode == 'failure':
    sys.exit(42)
if mode == 'help':
    os.execv(sys.executable, pipeline + ['--help'])
if mode == 'empty':
    print('[]')
    sys.exit(0)
if args[:3] != ['--rm', '-i', 'atlas-content-pipeline:latest']:
    sys.exit(64)
os.execv(sys.executable, pipeline + args[3:])
''', encoding='utf-8')
            docker.chmod(0o755)
            sleep = root / 'sleep'
            sleep.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            sleep.chmod(0o755)
            result = subprocess.run(
                ['/bin/bash', str(project / 'scripts' / 'deploy.sh'), 'docker'],
                cwd=root, input='', capture_output=True, text=True, timeout=10,
                env={'HOME': directory, 'PATH': directory + os.pathsep + os.defpath,
                     'PYTHONDONTWRITEBYTECODE': '1', 'SMOKE_MODE': mode,
                     'SMOKE_PIPELINE': str(project / 'scripts' /
                                           'getnote_frontmatter_pipeline.py'),
                     'SMOKE_ARGS': str(root / 'args.json')})
            args = json.loads((root / 'args.json').read_text())
        return result, args

    def test_smoke_check_runs_dry_run_on_synthetic_input(self):
        result, args = self.run_smoke_check('success')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Smoke test passed', result.stdout)
        self.assertIn('--dry-run', args)
        self.assertIn('--source', args)
        self.assertIn('/dev/stdin', args)

    def test_smoke_check_rejects_help_containing_dry_run(self):
        result, _ = self.run_smoke_check('help')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Smoke test passed', result.stdout)

    def test_smoke_check_rejects_empty_candidates(self):
        result, _ = self.run_smoke_check('empty')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Smoke test passed', result.stdout)

    def test_smoke_check_rejects_container_failure(self):
        result, _ = self.run_smoke_check('failure')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Smoke test passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
