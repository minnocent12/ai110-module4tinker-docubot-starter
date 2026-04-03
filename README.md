# DocuBot

DocuBot is a small documentation assistant that helps answer developer questions about a codebase.  
It can operate in three different modes:

1. **Naive LLM mode**  
   Sends the entire documentation corpus to a Gemini model and asks it to answer the question.

2. **Retrieval only mode**  
   Uses a simple indexing and scoring system to retrieve relevant snippets without calling an LLM.

3. **RAG mode (Retrieval Augmented Generation)**  
   Retrieves relevant snippets, then asks Gemini to answer using only those snippets.

The docs folder contains realistic developer documents (API reference, authentication notes, database notes), but these files are **just text**. They support retrieval experiments and do not require students to set up any backend systems.

---

## Setup
### 0. Install Python dependencies
1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows

### 1. Install Python dependencies

    pip install -r requirements.txt

### 2. Configure environment variables

Copy the example file:

    cp .env.example .env

Then edit `.env` to include your Gemini API key:

    GEMINI_API_KEY=your_api_key_here

If you do not set a Gemini key, you can still run retrieval only mode.

---

## Running DocuBot

Start the program:

    python main.py

Choose a mode:

- **1**: Naive LLM (Gemini reads the full docs)  
- **2**: Retrieval only (no LLM)  
- **3**: RAG (retrieval + Gemini)

You can use built in sample queries or type your own.

---

## Running Retrieval Evaluation (optional)

    python evaluation.py

This prints simple retrieval hit rates for sample queries.

---

## Modifying the Project

You will primarily work in:

- `docubot.py`  
  Implement or improve the retrieval index, scoring, and snippet selection.

- `llm_client.py`  
  Adjust the prompts and behavior of LLM responses.

- `dataset.py`  
  Add or change sample queries for testing.

---

## Requirements

- Python 3.9+
- A Gemini API key for LLM features (only needed for modes 1 and 3)
- No database, no server setup, no external services besides LLM calls

---

## Tech Fellow Notes

The core concept students need to understand is that retrieval and generation are separate responsibilities, and that a fluent, confident answer from an LLM is not the same as a grounded one. Without retrieval, the model answers from training data rather than the actual project docs. Students most commonly struggle with the scoring and ranking logic: they can implement `build_index` and `score_document` without fully understanding why a wrong document ranks higher than the right one, and tracing the failure requires printing per-document scores and comparing them against the query words that actually matched. AI tools were genuinely helpful for explaining what the retrieval pipeline was doing at each stage and for generating edge case queries to stress-test the guardrails, but they were misleading when the naive LLM produced long, well-formatted answers that sounded authoritative, so students need to be guided to ask not "does it sound right?" but "is it sourced?" The most important thing the three-mode comparison reveals is that RAG is a system design decision, not a model capability: improvements in answer quality came from better chunking, stop word filtering, and scoring logic, not from a smarter model. To guide a student without giving the answer, ask them to run the same question in all three modes, then point to a specific claim in the naive LLM answer and ask them to find the sentence in the docs that supports it. When they cannot, the case for retrieval makes itself.
