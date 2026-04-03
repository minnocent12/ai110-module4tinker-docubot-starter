# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**

DocuBot is a documentation assistant that answers developer questions grounded in a specific set of project documents. It is designed to avoid hallucination by retrieving relevant sections before generating answers, and to refuse when the docs do not support a response.

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

- Splitting on markdown headers keeps chunks semantically meaningful, but means sections with no header (e.g., a preamble paragraph) may be grouped under the document title rather than a descriptive header.
- Term frequency rewards documents that repeat query terms, which improves ranking but can over-weight verbose sections.
- `MIN_SCORE = 3` was tuned empirically on four test queries. A higher threshold reduces noise but risks missing relevant sections in shorter documents.
- Prefix matching (e.g., "token" matches "tokens") improves recall but can cause false positives for short query words that prefix unrelated longer words.

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

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Harmful — confident answer about OAuth, IdP flows, and AWS Cognito; none of these exist in this project | Helpful — returns correct sections, but raw markdown is hard to read | Helpful — concise answer citing `POST /api/login`, `AUTH_SECRET_KEY`, and source files | RAG missed `## Token Generation` section specifically; retrieval ranking issue |
| How do I connect to the database? | Harmful — generic guide covering MySQL, PostgreSQL, MongoDB, Node.js; none relevant to this project | Helpful — returns `DATABASE_URL` examples, `db.py` description, troubleshooting note | Helpful — precise answer: set `DATABASE_URL`, defaults to SQLite, `db.py` handles connections | Best RAG result of the four queries |
| Which endpoint lists all users? | Harmful — guesses `/users` or `/api/v1/users`, advises consulting docs it doesn't have | Helpful — returns `GET /api/users` section directly, though raw format buries the answer | Helpful — one sentence: `GET /api/users`, sourced from `API_REFERENCE.md` | RAG at its clearest; retrieval found the right section, LLM extracted the answer |
| How does a client refresh an access token? | Harmful — detailed explanation of OAuth 2.0 refresh token rotation, `grant_type`, confidential clients; none of this applies here | Helpful — returns `## Client Workflow` and `POST /api/refresh` sections correctly | Helpful — correct and concise: call `POST /api/refresh` with `Bearer <token>` in the header | All three steps worked well; Naive LLM's answer was technically accurate for OAuth but wrong for this project |
| What is the weather today? | Partially safe — model recognized it is out of scope and declined | Safe — guardrail triggered, returned "I do not know based on these docs." | Safe — guardrail triggered before LLM call, returned "I do not know based on these docs." | Unrelated query handled correctly by all three modes |

**What patterns did you notice?**

- **When does naive LLM look impressive but untrustworthy?** Every time it answered a question that has a real answer in the docs. The responses were long, structured, and confident — but described generic software patterns (OAuth, AWS Cognito, psycopg2) rather than the actual project. A developer reading the naive answer would not know they were getting the wrong system's documentation.

- **When is retrieval only clearly better?** When the answer needs to be traceable. Retrieval only always shows exactly which document and section the answer came from. It cannot fabricate. The weakness is that raw markdown sections require the developer to read and interpret them — there is no synthesis.

- **When is RAG clearly better than both?** On precise factual questions like "Which endpoint lists all users?" — RAG returned a single sentence with a source citation. Retrieval only returned three sections of raw markdown. Naive LLM guessed. RAG combined the accuracy of retrieval with the readability of generation.

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
