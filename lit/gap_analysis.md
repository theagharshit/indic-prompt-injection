# Gap Analysis and Novelty Check

*Literature checked up to 2026-10-30. Every work below was opened and read on its primary page (arXiv, ACL Anthology, proceedings, Zenodo, GitHub).*

## 1. What has been done

1. **IPI on tool-using agents is well benchmarked, but only in English.** Benchmarks include AgentDojo, InjecAgent, ASB, WASP, BIPIA, and AgentDAM. Defenses include spotlighting, StruQ, SecAlign, MELON, CaMeL, PIGuard, DataSentinel, and PromptGuard 2. None of their evaluations go beyond English. The one exception is PromptGuard 2, whose authors report detector AUC on machine translations into eight languages, Hindi among them.
2. **Multilingual and code-mixed jailbreaks are well studied for chat models.** Low-resource translation (Yong 2023, Deng 2024, Shen 2024), code-switching (CSRT, ACL 2025), Romanized Hinglish with phonetic perturbations (Aswal & Jaiswal 2025), Arabizi (Ghanim 2024), and Indic jailbreak and safety benchmarks (IndicJR, IndicSafe, SurakshaEval, IndicSafeEval, BanglaShield) all test **direct** harmful requests to **chat** models. None of them involve tools or injected data.
3. **Multilingual security for agents has started to appear.**
   - **MAPS** (EACL Findings 2026) translated ASB into 11 languages, Hindi among them. It reports average ASR of 47.3% across non-English languages against 32.7% in English. It does not cover Bengali or Telugu, code-mixed or Romanized text, task-language versus payload-language mismatch, or a per-defense analysis, and it does not use AgentDojo.
   - **MIPIAD** (arXiv, May 2026) is an English and Bangla IPI *detector* built on BIPIA templates. Its "end-to-end" evaluation is LLM-level, not tool-using agents.
   - **Sarvam-105B pilot** (arXiv 2608.15392, Aug 2026) tests IPI in English, Tamil, and Tanglish, using delimited untrusted text and one model. It has 24 injected trials, no tools, and no defenses.
   - **Multilingual RAG IPI** (JOCSTEC 2026) covers English and Indonesian in a RAG pipeline and varies query, body, and payload language separately. This is a mismatch design, but for RAG rather than agents and not for Indic languages.
   - **BabelDojo** (Faerber Lab GitHub, created 2026-10-13) is **a multilingual extension of AgentDojo** with injections in about 10 languages plus code-switched and Romanized text. It plans to evaluate at least 5 defenses (tool filter, spotlighting, PIGuard, DataSentinel, MELON, CaMeL) and to analyze attack language versus user language. Its target is ACL or EMNLP. **Status as of 2026-10-30: "the experiments have not been run yet"**, and no paper exists. Its candidate pool has 25 languages. The Indic and South Asian ones are Hindi, Bengali, Tamil, Urdu, Nepali, Hinglish, and Romanized Hindi. **Telugu is not in the pool.**

## 2. What has not been done (our space)

- No *published* results exist for IPI on an executable tool-using agent benchmark in **Bengali or Telugu**.
- No published study of IPI in agents uses **Romanized or code-mixed Indic** payloads. The only related work is a 24-trial, no-tool pilot on Tanglish.
- No published work runs a **task-language × payload-language matrix** on an agent benchmark. Only the RAG study (EN/ID) varies payload language separately.
- No published measurement shows how **AgentDojo's built-in defenses** degrade by language. These are `tool_filter`, `transformers_pi_detector`, `spotlighting_with_delimiting`, and `repeat_user_prompt`. The default PI detector's model card says it does not handle non-English prompts, so we expect this defense to fail in other languages, and we can show it.
- No work compares a detector inside its *claimed* language support with one outside it, inside an agent loop. PromptGuard 2 86M claims Hindi but not Bengali, Telugu, or Romanized text, so it gives a natural test.
- No such evaluation has been run under a **free-tier-only budget**, which matters for reproducibility by Global-South researchers.

## 3. Closest prior work vs. ours

| Work | Status | Languages | Code-mixed / Romanized? | Indirect injection? | Tool-using agents? | Defenses evaluated? | Task/payload mismatch? |
|---|---|---|---|---|---|---|---|
| MAPS [hofman2026maps] | EACL Findings 2026 | EN + 11 (incl. **HI**; no BN/TE) | No | ASB attacks, which mix direct and indirect injection plus memory poisoning | Yes (ASB) | Translate-to-English mitigation only | No |
| BabelDojo [babeldojo2026] | **Planned, no results** | ~10 from a pool of 25 (HI, BN, TA, UR, NE candidates; **no TE**) | **Yes (planned: Hinglish, Romanized Hindi)** | Yes | Yes (AgentDojo) | **Yes (planned, ≥5)** | **Yes (planned)** |
| MIPIAD [muhtadi2026mipiad] | arXiv May 2026 | EN, BN | No | Yes (BIPIA-style) | No (LLM-level) | Proposes a detector | No |
| Sarvam pilot [madhusudhanan2026visible] | arXiv Aug 2026 | EN, TA, Tanglish | Yes (Tanglish) | Yes | No (no tools) | No | No |
| Multilingual RAG IPI [prihananto2026crosslingual] | Journal 2026 | EN, ID | No | Yes | No (RAG) | Trust-boundary prompt | **Yes** |
| Uysal et al. [uysal2026empirical] | arXiv Jun 2026 | EN, TR, RU, ZH | No (encodings only) | **No (direct)** | No | No | No |
| CMP red-teaming [aswal2025cmp] | arXiv 2025 | EN, Hinglish | **Yes** | No (jailbreak) | No | No | No |
| IndicJR / IndicSafe / SurakshaEval | 2026 | 10–12 Indic (incl. BN, TE) | IndicJR: partly | No | No | No | No |
| Upadhayay [upadhayay2026hinglish] | Zenodo 2026 | Hinglish | **Yes** | Detector only | No | Proposes a detector | No |
| **Ours** | — | **EN, HI, Hinglish, BN, TE** | **Yes (Romanized + code-mixed; script as a controlled variable)** | **Yes** | **Yes (AgentDojo)** | **Yes (4 built-in + multilingual PromptGuard 2)** | **Yes (full 5×5 matrix)** |

## 4. Verdict

**Our contribution is still novel in published work, but it is no longer uncontested.** No published paper evaluates Indic or code-mixed indirect prompt injection on tool-using agents with defenses and a mismatch condition. However, **BabelDojo is a direct threat.** It announces almost the same design (multilingual AgentDojo, code-switched and Romanized text, defenses, attack-language versus user-language), comes from an established lab, and targets ACL or EMNLP. If it publishes first, our generic claim ("first multilingual AgentDojo") disappears. MAPS already covers the "agents are more vulnerable in Hindi" finding at a coarse level.

### Threats, ranked
1. **BabelDojo** (high). It overlaps on benchmark, defenses, code-mixing, and mismatch. It is not published, and it says it will run "3–4 open models and 1 API model".
2. **MAPS** (medium). It already shows higher agent ASR in Hindi. We must cite it and frame our Hindi result as a replication or extension, not a discovery.
3. **MIPIAD, the Sarvam pilot, BanglaShield, and Upadhayay** (low). Each covers a narrow slice (detector only, no tools, or chat only). Cite them as evidence that the gap exists.

### What we should change or emphasise
1. **Move fast and post a preprint first.** Aim for an arXiv preprint by December 2026, before ARR January 2027. Cite BabelDojo as concurrent or planned work, honestly.
2. **Position the paper as Indic-first and script-aware, not "multilingual".** Lead with these:
   - **Telugu**, a Dravidian language outside BabelDojo's pool, and Bengali, both with native-speaker-written (not only MT) payloads.
   - **Script as a controlled variable.** Test each Indic language in native script, Romanized form, and code-mixed form (for example Hindi-Devanagari, Hindi-Romanized, and Hinglish), and add Romanized Telugu or Bengali if possible. Prior jailbreak results conflict here: Aswal & Jaiswal find Romanization raises ASR, while IndicJR finds it lowers jailbreak success. Settling this question in the agent setting is a clean, citable contribution.
   - A **full 5×5 task-language × payload-language matrix**, including Indic user tasks with English payloads. This requires translating AgentDojo user prompts, not only the payloads.
   - **Detector language coverage as a hypothesis.** Compare ProtectAI DeBERTa (English-only by its card) with PromptGuard 2 86M (claims Hindi, not Bengali or Telugu). Our prediction is that detection fails where training coverage stops, and that Romanization defeats both.
3. Add an **analysis of the mechanism**: tokenization (tokens per payload, as IndicJR and CMP observe) correlated with ASR, and whether the agent translates or explains the injection before acting on it.
4. Report **worst-case-language** numbers, as Yong et al. 2025 recommend, together with confidence intervals.
5. Use the **free-tier constraint as a reproducibility feature**, and release translated payloads and code.

### Unverified leads (not cited)
- *"Detection and analysis of prompt injection in Indian multilingual large language models"*, Scientific Reports 2026 (DOI 10.1038/s41598-026-43883-0). The Nature, PMC, and PubMed pages could not be read (blocked or CAPTCHA). The Upadhayay Zenodo record lists this DOI as a related article, so it is probably a detection or classifier paper and probably not about agents. **Someone should read it manually before submission.**
