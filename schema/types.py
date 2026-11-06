"""Type definitions for atlas-content-pipeline."""

from typing import List, Dict, Optional, Any

# Valid categories for article classification
CATEGORY_VALUES = [
    'learn-chinese', 'hsk-prep', 'chinese-for-work', 'chinese-culture',
    'teaching-methods', 'language-learning', 'daily-life',
]

# Valid audience values
AUDIENCE_VALUES = [
    'beginner', 'elementary', 'intermediate', 'advanced',
    'teacher', 'self-learner',
]

# Valid intent values
INTENT_VALUES = [
    'exam', 'daily-life', 'business', 'travel', 'culture',
    'teaching', 'entertainment',
]

# Valid pilot priority values
PILOT_VALUES = ['p0', 'p1', 'p2', 'p3']

# Note dataclass
NoteDict = Dict[str, Any]
Frontmatter = Dict[str, Any]
