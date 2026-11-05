"""Text normalization for untrusted display fields."""

import unicodedata


def neutralize_text(value: str, *, allow_newlines: bool = True) -> str:
    """Remove bidi overrides and control characters from untrusted text.

    Newlines and tabs are kept for multi-line fields; every other control or
    format character is dropped so it cannot reorder or hide the stored value.
    """
    cleaned = []
    for character in value:
        category = unicodedata.category(character)
        if category in {"Cf", "Cs"}:
            continue
        if category.startswith("C"):
            if allow_newlines and character in {"\n", "\t"}:
                cleaned.append(character)
            continue
        cleaned.append(character)
    return "".join(cleaned)
