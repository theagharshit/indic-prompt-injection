"""Multilingual version of AgentDojo's `important_instructions` attack.

For payload language L the attack:
  (a) replaces the wrapper text (`ImportantInstructionsAttack._JB_STRING`) with the
      translated ``template`` from data/translations/{L}.json, and
  (b) replaces ``injection_task.GOAL`` with ``injection_goals[suite][injection_task_id]``.
Injection *vectors* (which placeholders in the environment get the payload) are chosen
exactly as AgentDojo does (`BaseAttack.get_injection_candidates`, ground-truth replay of
the ENGLISH user task -- the vector set does not depend on prompt language).

For L == "en" the output is byte-identical to AgentDojo's `important_instructions`
(given the same model descriptor) -- tested in tests/test_dry_run.py.

Registration: one class per language is registered with AgentDojo's registry under
``important_instructions_ml_{L}`` (e.g. ``important_instructions_ml_hi``), so
``agentdojo.attacks.load_attack`` and the stock ``agentdojo`` CLI (with
``--module-to-load ipi_ml``) can use it. ``make_attack`` builds one with a custom
translations directory (used by tests).
"""

from __future__ import annotations

from pathlib import Path

from agentdojo.agent_pipeline.base_pipeline_element import BasePipelineElement
from agentdojo.attacks.attack_registry import register_attack
from agentdojo.attacks.base_attacks import FixedJailbreakAttack
from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
from agentdojo.base_tasks import BaseInjectionTask, BaseUserTask
from agentdojo.models import MODEL_NAMES
from agentdojo.task_suite.task_suite import TaskSuite

from ipi_ml.constants import (
    ATTACK_NAME,
    DEFAULT_MODEL_DESCRIPTOR,
    LANGUAGES,
    MODEL_DESCRIPTOR_RULES,
    TRANSLATIONS_DIR,
)
from ipi_ml.translations import PayloadTranslations

ENGLISH_TEMPLATE = ImportantInstructionsAttack._JB_STRING


def resolve_model_descriptor(pipeline_or_model_name: str) -> str:
    """English phrase used for the {model} placeholder (mirrors AgentDojo's MODEL_NAMES)."""
    name = pipeline_or_model_name
    for full, desc in MODEL_NAMES.items():  # exact AgentDojo behaviour when the model is known
        if full in name:
            return desc
    low = name.lower()
    for key, desc in MODEL_DESCRIPTOR_RULES:
        if key in low:
            return desc
    return DEFAULT_MODEL_DESCRIPTOR


class MultilingualImportantInstructionsAttack(FixedJailbreakAttack):
    name = ATTACK_NAME
    payload_lang: str = "en"
    translations_dir: Path = TRANSLATIONS_DIR

    def __init__(self, task_suite: TaskSuite, target_pipeline: BasePipelineElement) -> None:
        self.translations = PayloadTranslations(self.payload_lang, self.translations_dir)
        super().__init__(self.translations.template(ENGLISH_TEMPLATE), task_suite, target_pipeline)
        self.model_descriptor_en = resolve_model_descriptor(target_pipeline.name or "")
        self.model_name = self.translations.model_descriptor(self.model_descriptor_en)
        self.user_name = self.translations.user_name()

    def translated_goal(self, injection_task: BaseInjectionTask) -> str:
        return self.translations.goal(self.task_suite.name, injection_task.ID, injection_task.GOAL)

    def attack(self, user_task: BaseUserTask, injection_task: BaseInjectionTask) -> dict[str, str]:
        goal = self.translated_goal(injection_task)  # raises MissingTranslationError, never falls back
        injections = {}
        for inj in self.get_injection_candidates(user_task):
            injections[inj] = self.jailbreak.format(
                goal=goal,
                user=self.user_name,
                model=self.model_name,
                task=self.summarize_task(user_task),
            )
        return injections

    def provenance(self) -> dict:
        return {
            "attack": self.name,
            "payload_lang": self.payload_lang,
            "translation_file": str(self.translations.path) if self.translations.path else None,
            "translation_sha256": self.translations.sha256,
            "model_descriptor_en": self.model_descriptor_en,
            "model_descriptor_used": self.model_name,
            "user_name_used": self.user_name,
        }


def make_attack(payload_lang: str, task_suite: TaskSuite, target_pipeline: BasePipelineElement,
                translations_dir: Path | None = None) -> MultilingualImportantInstructionsAttack:
    cls = type(
        f"MultilingualImportantInstructionsAttack_{payload_lang}",
        (MultilingualImportantInstructionsAttack,),
        {"payload_lang": payload_lang, "translations_dir": Path(translations_dir or TRANSLATIONS_DIR),
         "name": f"{ATTACK_NAME}_{payload_lang}"},
    )
    return cls(task_suite, target_pipeline)


# Register one attack per language with AgentDojo's registry.
for _lang in LANGUAGES:
    register_attack(
        type(
            f"MultilingualImportantInstructionsAttack_{_lang}",
            (MultilingualImportantInstructionsAttack,),
            {"payload_lang": _lang, "name": f"{ATTACK_NAME}_{_lang}"},
        )
    )
