# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**

DocuBot is a lightweight retrieval-augmented assistant designed to answer questions about a software project's internal documentation. It reads local doc files, finds relevant sections, and generates grounded answers, refusing to speculate when the docs do not contain enough evidence.

**What inputs does DocuBot take?**

- A natural language question from the user
- A folder of `.md` and `.txt` documentation files (the `docs/` directory)
- An optional Gemini API key to enable LLM-powered modes

**What outputs does DocuBot produce?**

- Mode 1: A free-form LLM-generated answer with no grounding in the docs
- Mode 2: Raw retrieved document sections, no generation
- Mode 3: A concise LLM-generated answer grounded only in retrieved sections, with source file citations

---

## 2. Retrieval Design

**How does your retrieval system work?**

- **Indexing:** At load time, each document is split into sections at markdown headers (`#` and `##`). Each section becomes its own retrieval unit. An inverted index maps lowercase word tokens to the filenames that contain them.
- **Scoring:** Stop words are removed from the query. Each remaining query word is matched against document tokens using term frequency and prefix matching (e.g., "endpoint" matches "endpoints"). The score is the total count of matching tokens in the section.
- **Selection:** Only sections scoring at or above `MIN_SCORE = 3` are considered. The top `k` sections are returned, sorted by score descending with ties broken by preferring shorter snippets.

**What tradeoffs did you make?**

| Tradeoff | Choice Made | Consequence |
|---|---|---|
| Speed vs. precision | Simple keyword overlap with term frequency | Fast and debuggable, but no semantic understanding |
| Simplicity vs. accuracy | No stemming, no TF-IDF, no embeddings | Easy to trace failures, but phrasing mismatches cause missed results |
| Recall vs. precision | `MIN_SCORE = 3` tuned on four queries | Allows some noise to avoid missing valid answers in shorter sections |
| Whole document vs. sections | Section-level chunking at markdown headers | More focused snippets, but sections without headers attach to the document title chunk |
| Exact match vs. variants | Prefix matching (e.g., "token" matches "tokens") | Improves recall for plurals and verb forms, but risks false positives for short query words |

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**

- **Naive LLM mode:** The LLM is called unconditionally with only the bare question — no doc context is provided. The model answers from its general training knowledge.
- **Retrieval only mode:** The LLM is never called. Retrieved sections are returned as-is. The answer is always traceable to a specific document and section.
- **RAG mode:** The retrieval pipeline runs first. If no sections pass the guardrail threshold, the LLM is never called and the system returns "I do not know based on these docs." Only when relevant sections are found does the LLM generate a response, using only those sections as context.

**What instructions do you give the LLM to keep it grounded?**

The RAG prompt instructs Gemini to:
- Answer using only the provided document snippets
- Cite which files the answer relies on
- Respond with "I do not know based on the docs I have." if the snippets do not contain enough evidence
- Never invent function names, endpoint paths, or configuration values not present in the snippets

---

## 4. Experiments and Comparisons

| Query | Naive LLM | Retrieval Only | RAG | Notes |
|-------|-----------|----------------|-----|-------|
| Where is the auth token generated? | ❌ Harmful — invented generic OAuth/IdP flows with no grounding in this codebase | ✅ Helpful — returned exact sections from `API_REFERENCE.md` and `AUTH.md` | ✅ Helpful — one precise sentence citing `POST /api/login`, `POST /api/refresh`, and the signing key | Naive mode answered a different, imaginary system |
| How do I connect to the database? | ❌ Harmful — produced a multi-language tutorial (Python, Node.js, psql) entirely unrelated to this project | ✅ Helpful — returned `DATABASE_URL` config and `db.py` overview from `DATABASE.md` | ✅ Helpful — clean answer citing `DATABASE_URL`, SQLite default, and `db.py` | Naive mode was fluent but completely wrong for this codebase |
| Which endpoint lists all users? | ⚠️ Partially helpful — correctly guessed `GET /api/users` by convention, but admitted it was guessing | ✅ Helpful — returned the exact endpoint with headers, response, and failure codes | ✅ Helpful — one-line answer: `GET /api/users`, sourced from `API_REFERENCE.md` | RAG was most useful here: accurate and concise |
| How does a client refresh an access token? | ❌ Harmful — described full OAuth 2.0 refresh token rotation with `client_secret` and `grant_type`; none of which exist in this system | ✅ Helpful — returned client workflow and `POST /api/refresh` spec | ✅ Helpful — answered correctly with the exact endpoint and header format | Naive mode described a completely different auth architecture |
| What is the weather today? | ⚠️ Partially safe — refused based on LLM self-judgment, not a system-enforced guardrail | ✅ Safe — guardrail fired, returned "I do not know based on these docs." | ✅ Safe — retrieval returned nothing, LLM was never called | Only RAG and Retrieval modes have a reliable, system-enforced refusal |

**What patterns did you notice?**

- **Naive LLM looks impressive but is untrustworthy.** For every question, it produced fluent, well-structured answers — but they described imaginary systems (OAuth servers, MongoDB, psql, JWT rotation) that have nothing to do with this project. Confidence does not equal correctness.

- **Retrieval only is accurate but hard to interpret.** The raw snippets contain the correct answer but require the reader to extract it themselves. It returns too much context (e.g., failure cases, unrelated endpoints) alongside the relevant information.

- **RAG consistently balances clarity and evidence.** Every RAG answer was 2-4 sentences, cited its sources, and contained only information present in the docs. It was the most useful mode for all four questions.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**

> **Failure case 1 — Naive LLM confidently answers the wrong system**
> Question: "Where is the auth token generated?"
> What happened: The model described OAuth 2.0 flows, Identity Providers, and AWS Cognito in detail. The actual answer (`generate_access_token` in `auth_utils.py`) was never mentioned.
> What should have happened: The system should have retrieved `AUTH.md ## Token Generation` and answered with the project-specific function and module name.

> **Failure case 2 — RAG misses the most relevant section**
> Question: "Where is the auth token generated?"
> What happened: RAG retrieved `## Authentication Endpoints`, `## Overview`, and `## Environment Variables` — but not `## Token Generation`, which contains the direct answer (`generate_access_token` in `auth_utils.py`).
> What should have happened: `## Token Generation` should have ranked first. The scoring algorithm likely ranked it lower because the section is shorter and the word "generated" does not appear verbatim in that section's text (the doc uses "created" instead). This is a vocabulary mismatch the retriever cannot resolve without stemming or synonym expansion.

**When should DocuBot say "I do not know based on the docs I have"?**

> 1. When the query topic does not appear in any document at all — for example, "What is the weather today?" or "How do I deploy to Kubernetes?" These topics are genuinely absent from the corpus.
> 2. When query words appear in the docs but no section scores high enough to constitute meaningful evidence — for example, a word like "version" might appear in passing in a setup note, but no section is actually about versioning. The `MIN_SCORE` threshold handles this case.

**What guardrails did you implement?**

> - **Guardrail 1 — Empty or stop-word-only queries:** If `meaningful_query_words()` returns an empty set (e.g., empty string, "where is the"), retrieval returns immediately with no results.
> - **Guardrail 2 — Topic not in corpus:** If the inverted index finds no candidate documents for any query word, retrieval returns no results.
> - **Guardrail 3 — Insufficient evidence:** If every candidate section scores below `MIN_SCORE = 3`, retrieval returns no results. This prevents weakly matching sections from reaching the LLM.
> - **LLM-level guardrail:** The RAG prompt explicitly instructs Gemini to refuse if the provided snippets do not support the answer, and never to invent facts not present in the snippets.

---

## 6. Limitations and Future Improvements

**Current limitations**

1. **Vocabulary mismatch:** The retriever matches exact tokens. "Generated" does not match "created", so the `## Token Generation` section was missed for "Where is the auth token generated?" Stemming or synonym expansion would help.
2. **Section granularity is fixed at headers:** Some sections are long and contain multiple sub-topics. Splitting only at `##` means a long section like `## Authentication Endpoints` returns both `POST /api/login` and `POST /api/refresh` even when only one is relevant.
3. **`full_corpus_text` uses chunks, not full docs:** Since `self.documents` stores section chunks, `full_corpus_text()` concatenates sections rather than original files. This loses original document structure and ordering for naive LLM mode.
4. **No semantic understanding:** The retriever cannot reason about meaning. "How do I log in?" and "How do I authenticate?" would retrieve different sections even though they mean the same thing.

**Future improvements**

1. **Stemming or lemmatization:** Reduce "generated", "generates", "generation" to a common root so vocabulary mismatches are reduced.
2. **Sub-section chunking:** Further split long sections (e.g., split `## Authentication Endpoints` into one chunk per endpoint) to improve precision.
3. **Embedding-based retrieval:** Replace keyword scoring with vector similarity so semantically related queries and documents match even without shared vocabulary.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**

> The primary risk is misplaced trust. Naive LLM mode produces long, confident, well-formatted answers that are wrong for this specific project. A developer who does not know the project well might follow those instructions — for example, implementing OAuth flows that the project does not support, or configuring an `AUTH_SECRET_KEY` incorrectly because the model described a different signing mechanism. In a production onboarding context, wrong documentation can cause security misconfigurations, data loss, or wasted engineering time.

**What instructions would you give real developers who want to use DocuBot safely?**

- Always prefer RAG mode (Mode 3) over Naive LLM mode (Mode 1) for project-specific questions. Naive mode answers from training data, not your docs.
- Check the source citations in RAG answers. If the cited file does not sound relevant to your question, treat the answer with skepticism and read the raw section in Mode 2.
- When DocuBot says "I do not know based on these docs", that is correct behaviour — do not re-phrase the question repeatedly hoping for a different answer. Go read the documentation directly.
- Do not add DocuBot to a production workflow without first auditing its answers against known-correct facts from your own documentation.

---
