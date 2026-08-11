import re


_WHITESPACE = re.compile(r"\s+")


def normalize_question(question: str) -> str:
    """Normalize cache/retrieval input without changing MTG punctuation or rule numbers."""
    return _WHITESPACE.sub(" ", question.strip()).casefold()

