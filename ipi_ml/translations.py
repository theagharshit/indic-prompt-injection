"""Loading and validating translated attack payloads and user-task prompts.

File formats (all UTF-8 JSON):

``data/translations/{L}.json`` -- payload (attacker-side) translations::

    {
      "language": "hi",
      "meta": {"translator": "...", "method": "human | MT+post-edit", ...},
      "template": "...{user}...{model}...{goal}...",        # translated important_instructions wrapper
      "model_descriptors": {"AI model developed by Google": "...", "AI assistant": "..."},
      "user_name": "Emma Johnson",                         # optional, defaults to English name
      "injection_goals": {"banking": {"injection_task_0": "...", ...}, ...}
    }

``data/translations/user_tasks_{L}.json`` -- user-side prompt translations::

    {"language": "hi", "meta": {...}, "user_prompts": {"banking": {"user_task_0": "...", ...}, ...}}

English ("en") never needs a file: the original AgentDojo strings are used.
Any missing key for a non-English language raises ``MissingTranslationError``;
there is NO fallback to English.
"""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from ipi_ml.constants import ATTACK_USER_NAME, DATA_DIR, LANGUAGES, SOURCE_LANG, TRANSLATIONS_DIR


class MissingTranslationError(KeyError):
    """Raised when a translation needed for a run is absent. Never caught silently."""

    def __str__(self) -> str:  # KeyError repr-quotes its message; make it readable
        return str(self.args[0]) if self.args else "missing translation"


class TranslationValidationError(ValueError):
    pass


# --------------------------------------------------------------------------------------
# Protected spans: substrings that AgentDojo's utility/security checks compare verbatim
# against environment state or model output (IBANs, e-mail addresses, URLs, quoted
# literals such as e-mail subjects, numbers, file names, identifiers). A translation that
# alters them changes the *task*, not just its language, so they must survive verbatim.
# --------------------------------------------------------------------------------------
_SPAN_PATTERNS = [
    ("quoted", re.compile(r"(?<![\w])'([^'\n]{1,300}?)'(?![\w])")),
    ("quoted", re.compile(r'"([^"\n]{1,300}?)"')),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("url", re.compile(r"https?://[^\s'\",]+")),
    ("domain", re.compile(r"\b(?:www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|org|net|io|co|in)(?:/[\w./-]*)?\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")),
    ("filename", re.compile(r"\b[\w-]+\.(?:txt|pdf|docx|xlsx|csv|json|md|jpg|png)\b")),
    ("identifier", re.compile(r"\b[A-Za-z0-9]+(?:_[A-Za-z0-9]+)+\b")),
    ("placeholder", re.compile(r"\{\w+\}")),
    ("number", re.compile(r"\d+(?:[.,:/-]\d+)*")),
]


def auto_protected_spans(text: str) -> list[str]:
    """Heuristically extract spans that must be preserved verbatim in translation.

    The output is a *starting point*; ``data/source_strings.json`` holds the curated
    list actually used for validation (it can be edited by hand).
    """
    spans: list[str] = []
    for _kind, pat in _SPAN_PATTERNS:
        for m in pat.finditer(text):
            s = m.group(1) if m.groups() else m.group(0)
            if _kind != "quoted":  # quoted literals are kept exactly (incl. final '?' / '.')
                s = s.strip().rstrip(".,;:!?")
            if s and s not in spans:
                spans.append(s)
    # keep only maximal spans (if A is inside B, B's presence implies A's)
    maximal = [s for s in spans if not any(s != o and s in o for o in spans)]
    return maximal


# Script checks: a translation into hi/bn/te must actually contain that script;
# Hinglish must be Romanized (no Devanagari).
_SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari
    "bn": (0x0980, 0x09FF),  # Bengali
    "te": (0x0C00, 0x0C7F),  # Telugu
}


def _script_ok(lang: str, text: str) -> tuple[bool, str]:
    if lang in _SCRIPT_RANGES:
        lo, hi = _SCRIPT_RANGES[lang]
        n = sum(lo <= ord(c) <= hi for c in text)
        return (n > 0, f"contains no characters in U+{lo:04X}-U+{hi:04X}")
    if lang == "hi_latn":
        n = sum(0x0900 <= ord(c) <= 0x097F for c in text)
        return (n == 0, "Hinglish must be Romanized but contains Devanagari")
    return True, ""


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@lru_cache
def load_source_strings(path: Path = DATA_DIR / "source_strings.json") -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `python extract_source_strings.py` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def _check_text(lang: str, key: str, src: str, tgt: str, spans: list[str], errors: list[str]) -> None:
    if not isinstance(tgt, str) or not tgt.strip():
        errors.append(f"[{key}] empty translation")
        return
    if lang != SOURCE_LANG and tgt.strip() == src.strip():
        errors.append(f"[{key}] identical to English source (untranslated?)")
    ok, why = _script_ok(lang, tgt)
    if not ok:
        errors.append(f"[{key}] script check failed: {why}")
    for s in spans:
        if s not in tgt:
            errors.append(f"[{key}] protected span not preserved verbatim: {s!r}")


def _placeholders(template: str) -> list[str]:
    import string

    return sorted({f for _, f, _, _ in string.Formatter().parse(template) if f is not None})


# --------------------------------------------------------------------------------------
# Payload translations
# --------------------------------------------------------------------------------------
class PayloadTranslations:
    """Attacker-side strings (template + injection GOALs) for one payload language."""

    def __init__(self, lang: str, translations_dir: Path = TRANSLATIONS_DIR):
        if lang not in LANGUAGES:
            raise ValueError(f"Unknown language {lang!r}; known: {sorted(LANGUAGES)}")
        self.lang = lang
        self.path: Path | None = None
        self.sha256: str | None = None
        self.data: dict = {}
        if lang != SOURCE_LANG:
            self.path = Path(translations_dir) / f"{lang}.json"
            if not self.path.exists():
                raise MissingTranslationError(f"Payload translation file not found: {self.path}")
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self.sha256 = file_sha256(self.path)
            if self.data.get("language") != lang:
                raise TranslationValidationError(
                    f"{self.path}: 'language' field is {self.data.get('language')!r}, expected {lang!r}"
                )

    def template(self, english_template: str) -> str:
        if self.lang == SOURCE_LANG:
            return english_template
        t = self.data.get("template")
        if not t:
            raise MissingTranslationError(f"[{self.lang}] 'template' missing in {self.path}")
        want, got = _placeholders(english_template), _placeholders(t)
        if want != got:
            raise TranslationValidationError(
                f"[{self.lang}] template placeholders {got} != English placeholders {want} in {self.path}"
            )
        return t

    def goal(self, suite: str, injection_task_id: str, english_goal: str) -> str:
        if self.lang == SOURCE_LANG:
            return english_goal
        try:
            g = self.data["injection_goals"][suite][injection_task_id]
        except KeyError:
            raise MissingTranslationError(
                f"[{self.lang}] injection goal missing: injection_goals.{suite}.{injection_task_id} in {self.path}"
            ) from None
        if not isinstance(g, str) or not g.strip():
            raise MissingTranslationError(f"[{self.lang}] empty goal for {suite}/{injection_task_id} in {self.path}")
        return g

    def model_descriptor(self, english_descriptor: str) -> str:
        if self.lang == SOURCE_LANG:
            return english_descriptor
        try:
            return self.data["model_descriptors"][english_descriptor]
        except KeyError:
            raise MissingTranslationError(
                f"[{self.lang}] model_descriptors[{english_descriptor!r}] missing in {self.path}"
            ) from None

    def user_name(self) -> str:
        return self.data.get("user_name", ATTACK_USER_NAME) if self.lang != SOURCE_LANG else ATTACK_USER_NAME


# --------------------------------------------------------------------------------------
# User-task prompt translations
# --------------------------------------------------------------------------------------
class UserPromptTranslations:
    def __init__(self, lang: str, translations_dir: Path = TRANSLATIONS_DIR):
        if lang not in LANGUAGES:
            raise ValueError(f"Unknown language {lang!r}; known: {sorted(LANGUAGES)}")
        self.lang = lang
        self.path: Path | None = None
        self.sha256: str | None = None
        self.data: dict = {}
        if lang != SOURCE_LANG:
            self.path = Path(translations_dir) / f"user_tasks_{lang}.json"
            if not self.path.exists():
                raise MissingTranslationError(f"User-task translation file not found: {self.path}")
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
            self.sha256 = file_sha256(self.path)
            if self.data.get("language") != lang:
                raise TranslationValidationError(
                    f"{self.path}: 'language' field is {self.data.get('language')!r}, expected {lang!r}"
                )

    def prompt(self, suite: str, user_task_id: str, english_prompt: str) -> str:
        if self.lang == SOURCE_LANG:
            return english_prompt
        try:
            p = self.data["user_prompts"][suite][user_task_id]
        except KeyError:
            raise MissingTranslationError(
                f"[{self.lang}] user prompt missing: user_prompts.{suite}.{user_task_id} in {self.path}"
            ) from None
        if not isinstance(p, str) or not p.strip():
            raise MissingTranslationError(f"[{self.lang}] empty user prompt for {suite}/{user_task_id}")
        return p


# --------------------------------------------------------------------------------------
# Whole-file validation (used by validate_translations.py and before every run)
# --------------------------------------------------------------------------------------
def validate_payload_file(lang: str, suites: list[str], source: dict, translations_dir: Path = TRANSLATIONS_DIR,
                          descriptors: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    try:
        pt = PayloadTranslations(lang, translations_dir)
    except (MissingTranslationError, TranslationValidationError) as e:
        return [str(e)]
    if lang == SOURCE_LANG:
        return []
    tmpl_src = source["templates"]["important_instructions"]
    try:
        t = pt.template(tmpl_src["text"])
        _check_text(lang, "template", tmpl_src["text"], t, tmpl_src.get("protected_spans", []), errors)
    except (MissingTranslationError, TranslationValidationError) as e:
        errors.append(str(e))
    for d in descriptors or []:
        try:
            pt.model_descriptor(d)
        except MissingTranslationError as e:
            errors.append(str(e))
    for suite in suites:
        for inj_id, item in source["suites"][suite]["injection_goals"].items():
            try:
                g = pt.goal(suite, inj_id, item["text"])
            except MissingTranslationError as e:
                errors.append(str(e))
                continue
            _check_text(lang, f"{suite}/{inj_id}", item["text"], g, item["protected_spans"], errors)
    return errors


def validate_user_task_file(lang: str, suites: list[str], source: dict,
                            translations_dir: Path = TRANSLATIONS_DIR) -> list[str]:
    errors: list[str] = []
    try:
        ut = UserPromptTranslations(lang, translations_dir)
    except (MissingTranslationError, TranslationValidationError) as e:
        return [str(e)]
    if lang == SOURCE_LANG:
        return []
    for suite in suites:
        for ut_id, item in source["suites"][suite]["user_prompts"].items():
            try:
                p = ut.prompt(suite, ut_id, item["text"])
            except MissingTranslationError as e:
                errors.append(str(e))
                continue
            _check_text(lang, f"{suite}/{ut_id}", item["text"], p, item["protected_spans"], errors)
    return errors
