"""Type definitions for atlas-content-pipeline."""

from typing import Dict, Any

# Valid categories for article classification
CATEGORY_VALUES = [
    'learn-chinese', 'hsk-prep', 'chinese-for-work', 'china-library', 'notes',
]

# Valid audience values
AUDIENCE_VALUES = [
    'beginner', 'lower-intermediate', 'intermediate', 'upper-intermediate',
    'advanced', 'mixed',
]

# Valid intent values
INTENT_VALUES = [
    'exam', 'daily-life', 'business', 'travel', 'culture', 'grammar',
    'pronunciation', 'reference', 'notes',
]

# Valid pilot priority values
PILOT_VALUES = ['p0', 'p1', 'p2']

# Note dataclass
NoteDict = Dict[str, Any]
Frontmatter = Dict[str, Any]
