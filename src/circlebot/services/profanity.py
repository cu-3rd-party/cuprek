"""Obfuscation-tolerant Russian / English profanity detector.

The detector never tries to be a linguistic analyser. It:

1. normalises the text (casefold, drop zero-width chars, map a few symbol
   look-alikes, drop soft/hard signs, collapse "ё" -> "е");
2. builds two views: ``squeezed`` (letters/digits/``*`` only, so "х у й" and
   "х.у.й" become "хуй") and ``spaced`` (word structure preserved, for patterns
   that need ``\\b`` anchors);
3. folds digit/letter look-alikes towards Cyrillic for the RU pass and towards
   Latin for the EN pass;
4. removes whitelisted fragments and runs curated regex lists from ``data/``.

All patterns live in editable text files so the word lists can be tuned without
touching code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# zero-width / invisible characters used to break up words
_DENOISE = dict.fromkeys(
    (
        0x00AD,  # soft hyphen
        0x034F,  # combining grapheme joiner
        0x061C,  # arabic letter mark
        0x180E,  # mongolian vowel separator
        0x200B,  # zero width space
        0x200C,  # zero width non-joiner
        0x200D,  # zero width joiner
        0x2060,  # word joiner
        0xFEFF,  # zero width no-break space
    ),
    None,
)

# symbols frequently used to spell letters (kept in Latin; the RU fold maps them on)
_SYMBOL_MAP = str.maketrans({"@": "a", "$": "s", "!": "i", "€": "e", "¡": "i"})

# letters, digits and the single-char censor mark "*"
_KEEP = r"0-9a-zа-я*"
_DROP_RE = re.compile(rf"[^{_KEEP}]+")
_MULTISPACE_RE = re.compile(r"\s+")
_SOFT_SIGNS_RE = re.compile(r"[ъь]")

# digit / homoglyph -> Cyrillic (RU pass)
_TO_CYR = str.maketrans(
    {
        "0": "о", "1": "и", "3": "з", "4": "ч", "6": "б", "8": "в", "9": "д",
        "a": "а", "b": "в", "c": "с", "e": "е", "h": "н", "k": "к", "m": "м",
        "o": "о", "p": "р", "t": "т", "x": "х", "y": "у",
    }
)

# digit / homoglyph -> Latin (EN pass)
_TO_LAT = str.maketrans(
    {
        "0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
        "а": "a", "в": "b", "е": "e", "к": "k", "м": "m", "н": "h", "о": "o",
        "р": "p", "с": "c", "т": "t", "у": "y", "х": "x", "і": "i", "ѕ": "s",
    }
)


def _fold(text: str) -> str:
    text = text.casefold().translate(_DENOISE).translate(_SYMBOL_MAP)
    text = text.replace("ё", "е")
    return _SOFT_SIGNS_RE.sub("", text)


def _views(text: str) -> tuple[str, str]:
    folded = _fold(text)
    squeezed = _DROP_RE.sub("", folded)
    spaced = _MULTISPACE_RE.sub(" ", _DROP_RE.sub(" ", folded)).strip()
    return squeezed, spaced


def _compile(patterns: list[str]) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def _read_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


@dataclass(frozen=True)
class _Lists:
    ru_squeezed: list[re.Pattern[str]]
    ru_spaced: list[re.Pattern[str]]
    ru_translit: list[re.Pattern[str]]
    ru_whitelist: tuple[str, ...]
    en_squeezed: list[re.Pattern[str]]
    en_spaced: list[re.Pattern[str]]
    en_whitelist: tuple[str, ...]


class ProfanityDetector:
    def __init__(self, lists: _Lists) -> None:
        self._l = lists

    @classmethod
    def load(cls, data_dir: str | Path) -> ProfanityDetector:
        d = Path(data_dir)
        return cls(
            _Lists(
                ru_squeezed=_compile(_read_list(d / "ru_squeezed.txt")),
                ru_spaced=_compile(_read_list(d / "ru_spaced.txt")),
                ru_translit=_compile(_read_list(d / "ru_translit.txt")),
                ru_whitelist=tuple(_read_list(d / "ru_whitelist.txt")),
                en_squeezed=_compile(_read_list(d / "en_squeezed.txt")),
                en_spaced=_compile(_read_list(d / "en_spaced.txt")),
                en_whitelist=tuple(_read_list(d / "en_whitelist.txt")),
            )
        )

    def is_profane(self, text: str | None) -> bool:
        return self.find_match(text) is not None

    def find_match(self, text: str | None) -> str | None:
        """Return the first matched fragment, or ``None`` if the text looks clean."""
        if not text or not text.strip():
            return None
        squeezed, spaced = _views(text)

        # -------- Russian (Cyrillic-folded) --------
        ru_sq = squeezed.translate(_TO_CYR)
        ru_sp = spaced.translate(_TO_CYR)
        for w in self._l.ru_whitelist:
            ru_sq = ru_sq.replace(w, " ")
            ru_sp = ru_sp.replace(w, " ")
        hit = _first(self._l.ru_squeezed, ru_sq) or _first(self._l.ru_spaced, ru_sp)
        if hit:
            return hit

        # -------- Russian transliterated with Latin letters (no folding) --------
        hit = _first(self._l.ru_translit, spaced) or _first(self._l.ru_translit, squeezed)
        if hit:
            return hit

        # -------- English (Latin-folded) --------
        en_sq = squeezed.translate(_TO_LAT)
        en_sp = spaced.translate(_TO_LAT)
        for w in self._l.en_whitelist:
            en_sq = en_sq.replace(w, " ")
            en_sp = re.sub(rf"\b{re.escape(w)}\b", " ", en_sp)
        return _first(self._l.en_squeezed, en_sq) or _first(self._l.en_spaced, en_sp)


def _first(patterns: list[re.Pattern[str]], text: str) -> str | None:
    for rx in patterns:
        m = rx.search(text)
        if m:
            return m.group(0)
    return None
