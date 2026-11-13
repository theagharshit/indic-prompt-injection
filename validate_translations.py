#!/usr/bin/env python
"""Validate translation files against data/source_strings.json.

Checks, per language: every required key present (template, model descriptors, all
injection goals / user prompts of the chosen suites); template placeholders identical to
English; protected spans preserved verbatim; expected script present (Hinglish: no
Devanagari); no string left identical to English. Exit code 1 on any error.

Usage: python validate_translations.py --langs hi hi_latn bn te --suites banking [--kind both]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ipi_ml.constants import ALL_MODEL_DESCRIPTORS, DATA_DIR, LANGUAGES, SUITES, TRANSLATIONS_DIR
from ipi_ml.translations import load_source_strings, validate_payload_file, validate_user_task_file


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--langs", nargs="+", default=[l for l in LANGUAGES if l != "en"], choices=sorted(LANGUAGES))
    ap.add_argument("--suites", nargs="+", default=["banking"], choices=SUITES)
    ap.add_argument("--kind", default="both", choices=["payload", "user", "both"])
    ap.add_argument("--translations-dir", type=Path, default=TRANSLATIONS_DIR)
    ap.add_argument("--source-strings", type=Path, default=DATA_DIR / "source_strings.json")
    a = ap.parse_args(argv)
    source = load_source_strings(a.source_strings)
    bad = 0
    for lang in a.langs:
        errs = []
        if a.kind in ("payload", "both"):
            errs += [f"payload: {e}" for e in validate_payload_file(lang, a.suites, source, a.translations_dir,
                                                                     ALL_MODEL_DESCRIPTORS)]
        if a.kind in ("user", "both"):
            errs += [f"user: {e}" for e in validate_user_task_file(lang, a.suites, source, a.translations_dir)]
        status = "OK" if not errs else f"{len(errs)} error(s)"
        print(f"[{lang}] {status}")
        for e in errs:
            print("   ", e)
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
