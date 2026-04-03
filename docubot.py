"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import re


class DocuBot:
    # common words that do not add much meaning for retrieval
    STOP_WORDS = {
        "a", "an", "the", "is", "are", "was", "were", "be", "been",
        "and", "or", "but", "in", "on", "at", "to", "for", "of", "with",
        "that", "this", "it", "its", "by", "from", "as", "into", "which",
        "where", "what", "how", "when", "who", "all", "any", "does", "do",
        "return", "returns", "get", "set", "not", "no", "if", "can", "will"
    }

    # minimum score a section must reach to be included in results;
    # below this threshold the query is considered unanswerable from the docs
    MIN_SCORE = 3

    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of (filename, section_text) tuples, one per section.
        Splitting at load time keeps the retrieval unit small and precise.
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")

        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as file:
                    text = file.read()
                filename = os.path.basename(path)
                # replace full doc with individual sections
                docs.extend(self.chunk_document(filename, text))

        return docs

    def chunk_document(self, filename, text):
        """
        Split a document into sections at markdown headers (## or #).
        Each section keeps its header as the first line so it is self-contained.
        Returns a list of (filename, section_text) tuples.
        """
        # split just before any line that starts with one or two # characters
        sections = re.split(r"\n(?=#{1,2} )", text)
        chunks = []
        for section in sections:
            section = section.strip()
            if section:
                chunks.append((filename, section))
        return chunks

    # -----------------------------------------------------------
    # Token Helper
    # -----------------------------------------------------------

    def tokenize(self, text):
        """
        Convert text into lowercase word tokens.
        """
        return re.findall(r"\b\w+\b", text.lower())

    def meaningful_query_words(self, query):
        """
        Extract meaningful query tokens by removing stop words.
        """
        return set(self.tokenize(query)) - self.STOP_WORDS

    def has_meaningful_query(self, query):
        """
        Return True if the query contains at least one meaningful term
        after stop word removal.
        """
        return len(self.meaningful_query_words(query)) > 0

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    def build_index(self, documents):
        """
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split into lowercase tokens and store each filename
        once per word.
        """
        index = {}

        for filename, text in documents:
            unique_words = set(self.tokenize(text))

            for word in unique_words:
                if word not in index:
                    index[word] = []
                index[word].append(filename)

        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """
        Return a simple relevance score for how well the text matches the query.

        Approach:
        - Remove stop words from the query so common words don't inflate scores
        - Count total occurrences of each query word in the document (term frequency)
        - Also match plural/singular variants (e.g. "endpoint" matches "endpoints")
        - Return the total count as the score
        """
        query_words = self.meaningful_query_words(query)
        doc_tokens = self.tokenize(text)

        # count every token that matches any query word, including prefix variants
        return sum(
            1 for token in doc_tokens
            if any(token.startswith(qw) or qw.startswith(token) for qw in query_words)
        )

    def retrieve(self, query, top_k=3):
        """
        Use the index and scoring function to select top_k relevant document
        snippets.

        Returns an empty list when there is not enough evidence to answer,
        which the answering methods treat as a refusal signal.
        """
        # guardrail 1: query has no meaningful terms after stop word removal
        # (empty string, punctuation-only, or all stop words like "where is the")
        if not self.has_meaningful_query(query):
            return []

        query_words = self.meaningful_query_words(query)

        # use the index to find documents that contain at least one query word
        candidate_filenames = set()
        for word in query_words:
            if word in self.index:
                candidate_filenames.update(self.index[word])

        # guardrail 2: none of the query terms appear anywhere in the docs
        if not candidate_filenames:
            return []

        # score every section inside candidate documents
        scored_results = []
        for filename, text in self.documents:
            if filename in candidate_filenames:
                score = self.score_document(query, text)
                if score >= self.MIN_SCORE:
                    scored_results.append((score, filename, text))

        # guardrail 3: query terms were found in the docs but no section
        # scored high enough — the topic is mentioned but not meaningfully documented
        if not scored_results:
            return []

        # sort by score descending; break ties by preferring shorter snippets
        scored_results.sort(key=lambda item: (-item[0], len(item[2])))

        return [(filename, text) for score, filename, text in scored_results[:top_k]]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)