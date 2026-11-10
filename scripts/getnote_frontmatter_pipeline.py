#!/usr/bin/env python3
"""Generate validated frontmatter from a GetNote Markdown export."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SOURCE = Path("input/getnote-export.md")
DEFAULT_OUTPUT = Path("output/pilot")
DEFAULT_MODEL = "claude-sonnet-4-0"
CLAUDE_CLI_CANDIDATES = [
    shutil.which("claude"),
]

CATEGORY_VALUES = {
    "learn-chinese",
    "hsk-prep",
    "chinese-for-work",
    "china-library",
    "notes",
}
AUDIENCE_VALUES = {
    "beginner",
    "lower-intermediate",
    "intermediate",
    "upper-intermediate",
    "advanced",
    "mixed",
}
INTENT_VALUES = {
    "daily-life",
    "exam",
    "business",
    "travel",
    "culture",
    "grammar",
    "pronunciation",
    "reference",
    "notes",
}
PILOT_VALUES = {"p0", "p1", "p2"}


@dataclass
class Note:
    note_id: int
    title: str
    created_at: str | None
    source_tags: list[str]
    raw_heading: str
    raw_markdown: str
    body_markdown: str
    score: int = 0


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=positive_int, default=30)
    parser.add_argument(
        "--selection",
        choices=["p0-seed", "first", "ids"],
        default="p0-seed",
    )
    parser.add_argument("--ids", type=str, default="")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--provider",
        choices=["auto", "claude-cli", "anthropic-api", "heuristic"],
        default="auto",
    )
    parser.add_argument("--max-body-chars", type=positive_int, default=6500)
    parser.add_argument("--max-retries", type=positive_int, default=2)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.selection == "ids":
        try:
            [int(part.strip()) for part in args.ids.split(",") if part.strip()]
        except ValueError:
            parser.error("--ids must be a comma-separated list of integers")
    return args


def parse_export(markdown: str) -> list[Note]:
    note_pattern = re.compile(
        r"^##\s+(?P<id>\d+)\.\s+(?P<title>.+?)\s+\{#note-\d+\}"
        r"(?:\s+\|\s+标签:\s+(?P<tags>.*?))?"
        r"(?:\s+\|\s+创建:\s+(?P<created>.*?))?\s*$",
        re.MULTILINE,
    )
    matches = list(note_pattern.finditer(markdown))
    notes: list[Note] = []

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        raw_note = markdown[start:end].strip()
        heading = match.group(0).strip()
        body = raw_note[len(heading) :].lstrip()
        tags_field = match.group("tags") or ""
        tags = [part.strip() for part in tags_field.split(",") if part.strip()]
        notes.append(
            Note(
                note_id=int(match.group("id")),
                title=match.group("title").strip(),
                created_at=(match.group("created") or "").strip() or None,
                source_tags=tags,
                raw_heading=heading,
                raw_markdown=raw_note,
                body_markdown=body,
            )
        )

    return notes


def score_note_for_p0(note: Note) -> int:
    text = f"{note.title}\n{' '.join(note.source_tags)}\n{note.body_markdown[:1500]}".lower()
    score = 0

    positive = {
        "hsk1": 45,
        "hsk2": 40,
        "hsk3": 35,
        "对外汉语": 24,
        "中文学习": 18,
        "日常": 18,
        "词汇": 18,
        "问候": 15,
        "时间表达": 20,
        "点餐": 20,
        "购物": 18,
        "打车": 18,
        "理发": 18,
        "天气": 16,
        "疑问词": 18,
        "拼音": 20,
        "发音": 20,
        "商务": 18,
        "职场": 16,
        "旅行": 16,
        "出行": 14,
        "用语": 16,
        "表达": 12,
        "课程讲解": 10,
    }
    negative = {
        "发芽报告": -60,
        "ai": -15,
        "产业": -8,
        "裁员": -12,
        "投资": -8,
        "深度解析": -6,
        "洞察": -6,
    }

    for token, weight in positive.items():
        if token in text:
            score += weight
    for token, weight in negative.items():
        if token in text:
            score += weight

    if note.note_id <= 120:
        score += 1
    return score


def select_notes(notes: list[Note], args: argparse.Namespace) -> list[Note]:
    if args.selection == "first":
        return notes[: args.limit]
    if args.selection == "ids":
        ids = {int(part.strip()) for part in args.ids.split(",") if part.strip()}
        return [note for note in notes if note.note_id in ids][: args.limit]

    for note in notes:
        note.score = score_note_for_p0(note)
    ranked = sorted(notes, key=lambda item: (-item.score, item.note_id))
    return ranked[: args.limit]


def slugify(text: str) -> str:
    value = text.lower().strip()
    replacements = {
        "hsk1": "hsk-1",
        "hsk2": "hsk-2",
        "hsk3": "hsk-3",
        "hsk4": "hsk-4",
        "hsk5": "hsk-5",
        "hsk6": "hsk-6",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    value = re.sub(r"[“”\"'‘’《》【】()（）:：，,、/]+", "-", value)
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff-]+", "", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if re.search(r"[\u4e00-\u9fff]", value):
        fallback = re.sub(r"[^a-z0-9-]+", "-", ascii_slug_seed(text))
        value = fallback.strip("-")
    return value or f"note-{int(time.time())}"


def ascii_slug_seed(text: str) -> str:
    seed = text.lower()
    replacements = {
        "中文": "chinese",
        "汉语": "mandarin",
        "课程": "course",
        "教学": "teaching",
        "词汇": "vocabulary",
        "语法": "grammar",
        "发音": "pronunciation",
        "拼音": "pinyin",
        "时间表达": "time-expressions",
        "点餐": "ordering-food",
        "购物": "shopping",
        "打车": "taxi",
        "理发": "haircut",
        "日常": "daily",
        "商务": "business",
        "旅行": "travel",
        "出行": "travel",
        "疑问词": "question-words",
        "会话": "conversation",
        "口语": "speaking",
        "问候": "greetings",
    }
    for src, dst in replacements.items():
        seed = seed.replace(src, dst)
    seed = re.sub(r"[^\w\s-]", " ", seed)
    seed = re.sub(r"\s+", "-", seed)
    return seed


def build_prompt(note: Note, max_body_chars: int) -> str:
    excerpt = note.body_markdown[:max_body_chars].strip()
    source_tags = ", ".join(note.source_tags) if note.source_tags else "none"
    return f"""
You are classifying Chinese-learning content for an Astro content site.

Return JSON only. No markdown fences. No prose outside JSON.

Classify this note into a tight MVP schema for atlas.zturnsgo.com.

Rules:
- Prefer learner-facing practical Chinese content over meta-analysis.
- Use `hsk-prep` only when the note clearly centers on HSK learning or exam prep.
- Use `learn-chinese` for practical daily Chinese, sentence patterns, speaking, travel Chinese, and beginner study content.
- Use `chinese-for-work` for workplace, business, executive, external-facing, or professional Chinese.
- Use `china-library` for culture, society, travel-in-China, food, festivals, and China context content.
- Use `notes` only if the content is reflective, broad, or not directly learner-usable.
- `hsk_level` must be null or 1-6. Infer from explicit HSK mention only. Do not guess from difficulty alone.
- `tags` must be 3-8 short English tags in kebab-case.
- `summary` must be in English and 1 sentence.
- `audience` must be one of: beginner, lower-intermediate, intermediate, upper-intermediate, advanced, mixed.
- `intent` must be one of: daily-life, exam, business, travel, culture, grammar, pronunciation, reference, notes.
- `pilot_priority`:
  - p0 for practical beginner/HSK 1-3/business intro/search-friendly content
  - p1 for useful but less core launch content
  - p2 for deeper notes or lower immediate SEO value

Output shape:
{{
  "title": "English-facing article title",
  "category": "learn-chinese|hsk-prep|chinese-for-work|china-library|notes",
  "hsk_level": null,
  "tags": ["tag-one", "tag-two", "tag-three"],
  "summary": "One sentence summary.",
  "audience": "beginner",
  "intent": "daily-life",
  "pilot_priority": "p0"
}}

Source note id: {note.note_id}
Source title: {note.title}
Source tags: {source_tags}
Source created_at: {note.created_at or "unknown"}

Source content:
{excerpt}
""".strip()


def frontmatter_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "title",
            "category",
            "hsk_level",
            "tags",
            "summary",
            "audience",
            "intent",
            "pilot_priority",
        ],
        "properties": {
            "title": {"type": "string"},
            "category": {"type": "string", "enum": sorted(CATEGORY_VALUES)},
            "hsk_level": {"type": ["integer", "null"], "enum": [None, 1, 2, 3, 4, 5, 6]},
            "tags": {
                "type": "array",
                "minItems": 3,
                "maxItems": 8,
                "items": {"type": "string"},
            },
            "summary": {"type": "string"},
            "audience": {"type": "string", "enum": sorted(AUDIENCE_VALUES)},
            "intent": {"type": "string", "enum": sorted(INTENT_VALUES)},
            "pilot_priority": {"type": "string", "enum": sorted(PILOT_VALUES)},
        },
    }


def resolve_provider(provider: str) -> str:
    if provider != "auto":
        return provider
    if any(path and Path(path).exists() for path in CLAUDE_CLI_CANDIDATES):
        return "claude-cli"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic-api"
    return "heuristic"


def resolve_claude_cli_path() -> str:
    for candidate in CLAUDE_CLI_CANDIDATES:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("`claude` CLI is not installed")


def call_claude_cli(prompt: str, model: str) -> str:
    claude_path = resolve_claude_cli_path()

    cmd = [
        claude_path,
        "-p",
        # Source notes are untrusted data, not permission to operate the host.
        "--tools",
        "",
        "--strict-mcp-config",
        "--disable-slash-commands",
        "--setting-sources",
        "",
        "--no-session-persistence",
        "--model",
        model,
        "--output-format",
        "text",
        "--json-schema",
        json.dumps(frontmatter_json_schema(), ensure_ascii=False),
    ]
    result = subprocess.run(
        cmd,
        input=prompt,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


def call_anthropic(prompt: str, model: str) -> str:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")

    payload = {
        "model": model,
        "max_tokens": 700,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Anthropic API error {exc.code}: {body}") from exc

    parsed = json.loads(raw)
    chunks = parsed.get("content", [])
    text_parts = [item.get("text", "") for item in chunks if item.get("type") == "text"]
    if not text_parts:
        raise RuntimeError("Anthropic response did not contain text content")
    return "\n".join(text_parts).strip()


def detect_hsk_level(text: str) -> int | None:
    lowered = text.lower()
    patterns = [
        (r"hsk\s*[一1]", 1),
        (r"hsk\s*[二2]", 2),
        (r"hsk\s*[三3]", 3),
        (r"hsk\s*[四4]", 4),
        (r"hsk\s*[五5]", 5),
        (r"hsk\s*[六6]", 6),
    ]
    for pattern, level in patterns:
        if re.search(pattern, lowered):
            return level
    return None


def infer_category_intent(note: Note) -> tuple[str, str]:
    title_text = f"{note.title}\n{' '.join(note.source_tags)}".lower()
    body_text = note.body_markdown[:1600].lower()
    combined_text = f"{title_text}\n{body_text}"

    strong_business_tokens = [
        "商务",
        "职场",
        "外贸",
        "商务出差",
        "开会",
        "会议",
        "客户",
        "谈判",
        "工作邮件",
        "微信沟通",
        "企业",
    ]
    learning_tokens = [
        "对外汉语",
        "中文学习",
        "中文教学",
        "日常用语",
        "词汇教学",
        "课程讲解",
        "会话课",
        "一对一教学",
    ]
    travel_tokens = ["旅行", "出行", "打车", "购物", "点餐", "理发", "方向", "用餐"]
    culture_tokens = ["文化", "节日", "历史", "社会", "城市", "饮食", "习俗"]

    if detect_hsk_level(title_text) is not None or "考试" in title_text or "备考" in title_text:
        return "hsk-prep", "exam"
    if any(token in title_text for token in strong_business_tokens):
        return "chinese-for-work", "business"
    if any(token in title_text for token in ["发音", "拼音", "声母", "韵母", "音调"]):
        return "learn-chinese", "pronunciation"
    if any(token in title_text for token in ["语法", "疑问词", "补语", "语序", "的字"]):
        return "learn-chinese", "grammar"
    if any(token in title_text for token in travel_tokens):
        return "learn-chinese", "travel" if any(token in title_text for token in ["旅行", "出行", "打车"]) else "daily-life"
    if any(token in title_text for token in ["问候", "时间表达", "常用", "日常", "词汇", "会话", "口语", "表达"]):
        return "learn-chinese", "daily-life"
    if any(token in title_text for token in culture_tokens) and not any(token in title_text for token in learning_tokens):
        return "china-library", "culture"
    if any(token in title_text for token in learning_tokens):
        return "learn-chinese", "daily-life"
    if any(token in title_text for token in culture_tokens):
        return "learn-chinese", "culture"
    return "notes", "notes"


def infer_audience(hsk_level: int | None, intent: str, note: Note) -> str:
    text = f"{note.title}\n{' '.join(note.source_tags)}".lower()
    if hsk_level in {1, 2}:
        return "beginner"
    if hsk_level == 3:
        return "lower-intermediate"
    if hsk_level in {4}:
        return "intermediate"
    if hsk_level in {5, 6}:
        return "upper-intermediate"
    if any(token in text for token in ["基础", "日常", "问候", "常用"]):
        return "beginner"
    if intent in {"business", "culture", "notes"}:
        return "mixed"
    return "lower-intermediate"


def infer_tags(note: Note, category: str, intent: str, hsk_level: int | None) -> list[str]:
    text = f"{note.title}\n{' '.join(note.source_tags)}\n{note.body_markdown[:3000]}".lower()
    ordered: list[str] = []

    def add(tag: str) -> None:
        if tag not in ordered:
            ordered.append(tag)

    category_defaults = {
        "learn-chinese": ["mandarin", "chinese-learning"],
        "hsk-prep": ["hsk", "mandarin", "exam-prep"],
        "chinese-for-work": ["business-chinese", "mandarin", "workplace"],
        "china-library": ["china", "culture", "mandarin-context"],
        "notes": ["teaching-notes", "mandarin", "reference"],
    }
    for tag in category_defaults[category]:
        add(tag)

    if hsk_level is not None:
        add(f"hsk-{hsk_level}")

    keyword_map = [
        ("时间", "time-expressions"),
        ("点餐", "ordering-food"),
        ("打车", "taxi-chinese"),
        ("购物", "shopping-chinese"),
        ("理发", "haircut-chinese"),
        ("问候", "greetings"),
        ("疑问词", "question-words"),
        ("语法", "grammar"),
        ("补语", "complements"),
        ("拼音", "pinyin"),
        ("发音", "pronunciation"),
        ("天气", "weather"),
        ("词汇", "vocabulary"),
        ("口语", "speaking"),
        ("会话", "conversation"),
        ("旅行", "travel-chinese"),
        ("出行", "travel-chinese"),
        ("商务", "business-chinese"),
        ("职场", "work-culture"),
        ("文化", "china-culture"),
        ("节日", "festivals"),
        ("历史", "china-history"),
    ]
    for keyword, tag in keyword_map:
        if keyword in text:
            add(tag)

    if intent == "daily-life":
        add("daily-chinese")
    elif intent == "exam":
        add("exam-chinese")
    elif intent == "business":
        add("professional-mandarin")
    elif intent == "culture":
        add("china-insight")
    elif intent == "pronunciation":
        add("sound-system")

    return ordered[:8] if len(ordered) >= 3 else (ordered + ["reference"])[:3]


def infer_priority(category: str, intent: str, hsk_level: int | None, note: Note) -> str:
    text = f"{note.title}\n{' '.join(note.source_tags)}".lower()
    if category == "hsk-prep" and (hsk_level is None or hsk_level <= 3):
        return "p0"
    if intent in {"daily-life", "travel", "grammar", "pronunciation", "business"}:
        return "p0"
    if any(token in text for token in ["日常", "问候", "常用", "时间表达", "点餐", "打车", "购物"]):
        return "p0"
    if category in {"china-library", "hsk-prep", "chinese-for-work"}:
        return "p1"
    return "p2"


def english_title(note: Note, category: str, intent: str, hsk_level: int | None) -> str:
    title = note.title
    replacements = [
        ("对外汉语", "Mandarin"),
        ("中文", "Chinese"),
        ("汉语", "Mandarin"),
        ("课程", "Lesson"),
        ("教学", "Teaching"),
        ("词汇", "Vocabulary"),
        ("日常用语", "Daily Expressions"),
        ("问候", "Greetings"),
        ("疑问词", "Question Words"),
        ("时间表达", "Time Expressions"),
        ("打车", "Taxi"),
        ("点餐", "Ordering Food"),
        ("购物", "Shopping"),
        ("理发", "Haircut"),
        ("发音", "Pronunciation"),
        ("拼音", "Pinyin"),
        ("语法", "Grammar"),
        ("商务", "Business"),
        ("口语", "Speaking"),
    ]
    title_en = title
    for src, dst in replacements:
        title_en = title_en.replace(src, dst)
    title_en = re.sub(r"[：:]+", " - ", title_en)
    title_en = re.sub(r"\s+", " ", title_en).strip(" -")
    if re.search(r"[\u4e00-\u9fff]", title_en):
        if category == "hsk-prep" and hsk_level:
            return f"HSK {hsk_level} Chinese Lesson"
        mapping = {
            "daily-life": "Practical Daily Chinese Lesson",
            "travel": "Travel Chinese Lesson",
            "grammar": "Chinese Grammar Lesson",
            "pronunciation": "Chinese Pronunciation Lesson",
            "business": "Business Chinese Lesson",
            "culture": "China Culture Note",
            "notes": "Chinese Teaching Note",
        }
        return mapping.get(intent, "Chinese Learning Note")
    return title_en[:140]


def english_summary(category: str, intent: str, hsk_level: int | None, tags: list[str]) -> str:
    topic = ", ".join(tags[:3])
    if category == "hsk-prep" and hsk_level is not None:
        return f"A learner-facing HSK {hsk_level} note covering {topic} for practical review and exam preparation."
    if intent == "business":
        return f"A business Chinese note focused on {topic} for workplace communication and China-facing conversations."
    if intent == "travel":
        return f"A practical Chinese lesson centered on {topic} for travel, daily navigation, and real-life use."
    if intent == "grammar":
        return f"A Chinese grammar-focused lesson covering {topic} for clearer sentence building and practical usage."
    if intent == "pronunciation":
        return f"A pronunciation-focused Chinese lesson covering {topic} to improve sound accuracy and learner confidence."
    if category == "china-library":
        return f"A China library entry that explains {topic} through language, culture, and everyday context."
    if category == "learn-chinese":
        return f"A practical Chinese learning note covering {topic} for daily speaking and beginner-friendly study."
    return f"A structured teaching note covering {topic} for the Atlas content system."


def heuristic_frontmatter(note: Note) -> dict[str, Any]:
    title_scope = f"{note.title}\n{' '.join(note.source_tags)}"
    hsk_level = detect_hsk_level(title_scope)
    category, intent = infer_category_intent(note)
    tags = infer_tags(note, category, intent, hsk_level)
    audience = infer_audience(hsk_level, intent, note)
    pilot_priority = infer_priority(category, intent, hsk_level, note)
    return {
        "title": english_title(note, category, intent, hsk_level),
        "category": category,
        "hsk_level": hsk_level,
        "tags": tags,
        "summary": english_summary(category, intent, hsk_level, tags),
        "audience": audience,
        "intent": intent,
        "pilot_priority": pilot_priority,
    }


def call_model(prompt: str, model: str, provider: str) -> str:
    if provider == "claude-cli":
        return call_claude_cli(prompt, model)
    if provider == "anthropic-api":
        return call_anthropic(prompt, model)
    if provider == "heuristic":
        raise RuntimeError("Heuristic provider should not call remote model")
    raise RuntimeError(f"Unsupported provider: {provider}")


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


def validate_frontmatter(data: dict[str, Any]) -> list[str]:
    if not isinstance(data, dict):
        return ["frontmatter must be an object"]
    errors: list[str] = []
    required = [
        "title",
        "category",
        "hsk_level",
        "tags",
        "summary",
        "audience",
        "intent",
        "pilot_priority",
    ]
    for field in required:
        if field not in data:
            errors.append(f"missing field: {field}")
    if set(data) - set(required):
        errors.append("unexpected frontmatter fields")

    if errors:
        return errors

    if not isinstance(data["title"], str) or not (4 <= len(data["title"]) <= 140):
        errors.append("title must be 4-140 chars")
    if not isinstance(data["category"], str) or data["category"] not in CATEGORY_VALUES:
        errors.append("invalid category")
    if data["hsk_level"] is not None and (
        type(data["hsk_level"]) is not int or not 1 <= data["hsk_level"] <= 6
    ):
        errors.append("invalid hsk_level")
    tags = data["tags"]
    if not isinstance(tags, list) or not (3 <= len(tags) <= 8):
        errors.append("tags must have 3-8 items")
    else:
        for tag in tags:
            if not isinstance(tag, str) or len(tag) < 2 or len(tag) > 32:
                errors.append(f"invalid tag: {tag!r}")
                continue
            if re.search(r"[A-Z\s]", tag):
                errors.append(f"tag must be kebab-case-ish: {tag!r}")
    if not isinstance(data["summary"], str) or not (24 <= len(data["summary"]) <= 220):
        errors.append("summary must be 24-220 chars")
    if not isinstance(data["audience"], str) or data["audience"] not in AUDIENCE_VALUES:
        errors.append("invalid audience")
    if not isinstance(data["intent"], str) or data["intent"] not in INTENT_VALUES:
        errors.append("invalid intent")
    if not isinstance(data["pilot_priority"], str) or data["pilot_priority"] not in PILOT_VALUES:
        errors.append("invalid pilot_priority")
    return errors


def build_output_slug(data: dict[str, Any], note: Note) -> str:
    base = slugify(data["title"])
    return f"{base}--note-{note.note_id}"


def format_frontmatter(data: dict[str, Any], note: Note, slug: str) -> str:
    merged = {
        "title": data["title"].strip(),
        "slug": slug,
        "category": data["category"],
        "hsk_level": data["hsk_level"],
        "tags": data["tags"],
        "summary": data["summary"].strip(),
        "audience": data["audience"],
        "intent": data["intent"],
        "pilot_priority": data["pilot_priority"],
        "draft": True,
        "source_note_id": note.note_id,
        "source_title": note.title,
        "source_created_at": note.created_at,
        "source_tags": note.source_tags,
        "generated_at": dt.datetime.now().replace(microsecond=0).isoformat(),
    }
    lines = ["---"]
    for key, value in merged.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
            lines.append(f"{key}: {rendered}")
        elif value is None:
            lines.append(f"{key}: null")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {json.dumps(str(item), ensure_ascii=False)}")
        else:
            lines.append(f"{key}: {json.dumps(str(value), ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def write_note(output_dir: Path, data: dict[str, Any], note: Note) -> Path:
    category_dir = output_dir / data["category"]
    category_dir.mkdir(parents=True, exist_ok=True)
    slug = build_output_slug(data, note)
    path = category_dir / f"{slug}.md"
    content = f"{format_frontmatter(data, note, slug)}\n\n{note.body_markdown.strip()}\n"
    path.write_text(content, encoding="utf-8")
    return path


def ensure_dirs(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "manifests").mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    try:
        source = args.source.read_text(encoding="utf-8", errors="ignore")
    except FileNotFoundError:
        print(
            f"Input file not found: {args.source}. "
            "Use --source to specify a GetNote export.",
            file=sys.stderr,
        )
        return 1
    notes = parse_export(source)
    selected = select_notes(notes, args)

    if args.dry_run:
        payload = [
            {
                "note_id": note.note_id,
                "title": note.title,
                "source_tags": note.source_tags,
                "score": note.score,
            }
            for note in selected
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    provider = resolve_provider(args.provider)
    ensure_dirs(args.output_dir)
    manifest: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for note in selected:
        if args.verbose:
            print(
                f"[atlas-pipeline] classify note {note.note_id}: {note.title}",
                file=sys.stderr,
                flush=True,
            )
        prompt = build_prompt(note, args.max_body_chars)
        parsed: dict[str, Any] | None = None
        errors: list[str] = []

        for attempt in range(1, args.max_retries + 1):
            try:
                if provider == "heuristic":
                    parsed = heuristic_frontmatter(note)
                else:
                    response_text = call_model(prompt, args.model, provider)
                    parsed = extract_json(response_text)
                errors = validate_frontmatter(parsed)
                if not errors:
                    break
                prompt = (
                    build_prompt(note, args.max_body_chars)
                    + "\n\nPrevious output failed validation with these errors:\n"
                    + "\n".join(f"- {error}" for error in errors)
                    + "\nReturn corrected JSON only."
                )
            except Exception as exc:  # noqa: BLE001
                errors = [str(exc)]
                if attempt >= args.max_retries:
                    parsed = None
                time.sleep(1.2)

        if parsed is None or errors:
            skipped.append(
                {
                    "note_id": note.note_id,
                    "title": note.title,
                    "errors": errors,
                }
            )
            continue

        path = write_note(args.output_dir, parsed, note)
        manifest.append(
            {
                "note_id": note.note_id,
                "title": note.title,
                "output_path": str(path),
                "category": parsed["category"],
                "hsk_level": parsed["hsk_level"],
                "tags": parsed["tags"],
                "pilot_priority": parsed["pilot_priority"],
            }
        )
        time.sleep(0.8)

    manifest_path = args.output_dir / "manifests" / "pilot-manifest.json"
    skipped_path = args.output_dir / "manifests" / "skipped.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    skipped_path.write_text(json.dumps(skipped, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "provider": provider,
                "selected": len(selected),
                "written": len(manifest),
                "skipped": len(skipped),
                "manifest": str(manifest_path),
                "skipped_manifest": str(skipped_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
