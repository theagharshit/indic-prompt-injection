"""Shared constants. Everything that defines an experimental condition lives here."""

from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = CODE_DIR / "data"
TRANSLATIONS_DIR = DATA_DIR / "translations"

# AgentDojo benchmark version used for every run (latest in agentdojo 0.1.35).
BENCHMARK_VERSION = "v1.2.2"

# Language codes used throughout (file names, CLI flags, result keys).
LANGUAGES = {
    "en": "English (control; original AgentDojo strings, no translation file)",
    "hi": "Hindi (Devanagari)",
    "hi_latn": "Hinglish (Romanized, code-mixed Hindi-English)",
    "bn": "Bengali (Bengali script)",
    "te": "Telugu (Telugu script)",
}
SOURCE_LANG = "en"

# Victim user name used by AgentDojo's `important_instructions` attack.
ATTACK_USER_NAME = "Emma Johnson"

# How the attack addresses the victim model ({model} placeholder). AgentDojo
# hard-codes a table (agentdojo.models.MODEL_NAMES) that does not know our
# free-tier models, so we resolve by substring.  Values for gemini / llama
# are exactly what AgentDojo uses for its own Gemini / Llama entries.
MODEL_DESCRIPTOR_RULES = [
    ("gemini", "AI model developed by Google"),
    ("gemma", "AI model developed by Google"),
    ("llama", "AI assistant"),
    ("qwen", "AI assistant"),
    ("mistral", "AI assistant"),
    ("deepseek", "AI assistant"),
    ("gpt", "GPT-4"),
    ("claude", "Claude"),
]
DEFAULT_MODEL_DESCRIPTOR = "AI assistant"
ALL_MODEL_DESCRIPTORS = sorted({d for _, d in MODEL_DESCRIPTOR_RULES} | {DEFAULT_MODEL_DESCRIPTOR})

# Defenses supported by AgentDojo 0.1.35 (agentdojo.agent_pipeline.agent_pipeline.DEFENSES)
DEFENSES = ["none", "tool_filter", "transformers_pi_detector", "spotlighting_with_delimiting", "repeat_user_prompt"]

SUITES = ["workspace", "travel", "banking", "slack"]

# Name of the multilingual attack in AgentDojo's registry.
ATTACK_NAME = "important_instructions_ml"
