"""Retrieval-augmented generation: a small, local, real retrieval pipeline.

    knowledge_base/*.md -> chunks (by heading, ~120 words, 30-word overlap)
      -> TF-IDF (word 1-2-grams) and LSA (TruncatedSVD) embeddings, L2-normalised
      -> hybrid cosine score = 0.5 * tfidf + 0.5 * lsa -> top-k above a threshold

TF-IDF matches exact terms ("EMI", "SIP"); LSA matches related wording ("rainy day savings"
~ "emergency fund"). The index is built in memory (milliseconds for this corpus) and rebuilt
automatically when any knowledge-base file changes. An empty or missing knowledge base simply
yields no results; the coach still answers from the user's own data.
"""

import hashlib
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

KNOWLEDGE_DIR = Path(__file__).resolve().parents[3] / "knowledge_base"
CHUNK_WORDS = 120
OVERLAP_WORDS = 30
MAX_LSA_DIMS = 64
DEFAULT_K = 3
MIN_SCORE = 0.12
RELATIVE_MIN = 0.5  # secondary hits must score at least half of the best hit


@dataclass(frozen=True)
class Chunk:
    id: str
    doc: str  # file stem
    title: str  # document title (first heading)
    heading: str  # section heading
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def load_chunks(directory: Path = KNOWLEDGE_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title_match = re.search(r"^# (.+)$", text, flags=re.MULTILINE)
        title = title_match.group(1).strip() if title_match else path.stem
        for section in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
            heading, _, body = section.partition("\n")
            body = re.sub(r"^\s*[-*]\s+", "", body, flags=re.MULTILINE)  # list markers
            words = body.split()
            step = CHUNK_WORDS - OVERLAP_WORDS
            for n, start in enumerate(range(0, max(len(words) - OVERLAP_WORDS, 1), step)):
                piece = " ".join(words[start : start + CHUNK_WORDS])
                if piece:
                    chunks.append(
                        Chunk(
                            f"{path.stem}#{len(chunks)}", path.stem, title, heading.strip(), piece
                        )
                    )
                if n > 50:  # guard against pathological files
                    break
    return chunks


class Index:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        documents = [f"{c.title}. {c.heading}. {c.text}" for c in chunks]
        self.tfidf = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english")
        tfidf_matrix = self.tfidf.fit_transform(documents)
        self.tfidf_matrix = normalize(tfidf_matrix)
        dims = min(MAX_LSA_DIMS, len(chunks) - 1, tfidf_matrix.shape[1] - 1)
        self.svd = TruncatedSVD(n_components=max(dims, 1), random_state=0)
        self.lsa_matrix = normalize(self.svd.fit_transform(tfidf_matrix))

    def search(self, query: str, k: int = DEFAULT_K, min_score: float = MIN_SCORE) -> list[Hit]:
        q = self.tfidf.transform([query])
        if q.nnz == 0:
            return []
        tfidf_scores = (self.tfidf_matrix @ normalize(q).T).toarray().ravel()
        lsa_scores = self.lsa_matrix @ normalize(self.svd.transform(q)).ravel()
        scores = 0.5 * tfidf_scores + 0.5 * lsa_scores
        hits, seen_docs = [], set()
        for i in np.argsort(-scores):
            if scores[i] < min_score or len(hits) == k:
                break
            if hits and scores[i] < RELATIVE_MIN * hits[0].score:
                break
            chunk = self.chunks[i]
            if chunk.doc in seen_docs:  # one chunk per document keeps sources diverse
                continue
            seen_docs.add(chunk.doc)
            hits.append(Hit(chunk, float(scores[i])))
        return hits


def _fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(directory.glob("*.md")):
        digest.update(path.name.encode())
        digest.update(str(path.stat().st_mtime_ns).encode())
    return digest.hexdigest()


@lru_cache(maxsize=4)
def _index(directory: str, fingerprint: str) -> Index | None:
    chunks = load_chunks(Path(directory))
    return Index(chunks) if len(chunks) >= 2 else None


def retrieve(query: str, k: int = DEFAULT_K, directory: Path = KNOWLEDGE_DIR) -> list[Hit]:
    if not directory.exists():
        return []
    index = _index(str(directory), _fingerprint(directory))
    return index.search(query, k) if index else []
