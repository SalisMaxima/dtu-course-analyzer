"""Course-to-course similarity from description embeddings.

Courses are embedded from their catalogue text and ranked by cosine similarity.
Pairs linked by "Not applicable together with" are equivalent courses, so they
are never listed as each other's neighbours.
"""

import re
from typing import Callable, Iterable

DEFAULT_MODEL = "google/embeddinggemma-2"
DEFAULT_TOP_K = 10
# Symmetric task prefix from the EmbeddingGemma 2 model card
SIMILARITY_PROMPT = "SentenceSimilarity"
TEXT_FIELDS = ("general_objectives", "learning_objectives", "content")

# Sentences repeated on every course page carry no signal and dilute the text
BOILERPLATE = re.compile(
    r"A student who has met the objectives of the course will be able to:?|"
    r"En studerende, der fuldt ud har opfyldt kursets mål, vil kunne:?",
    re.IGNORECASE,
)
LEADING_CODE = re.compile(r"^[0-9A-Z]{5}\s+")


def course_title(course: dict) -> str:
    """English name without the course-number prefix, falling back to Danish."""
    return LEADING_CODE.sub("", course.get("name_en") or "").strip() or course.get("name", "")


def similarity_text(title: str, details: dict) -> str | None:
    """Text embedded for a course, or None when the page had no description."""
    sections = [BOILERPLATE.sub(" ", details.get(field, "")) for field in TEXT_FIELDS]
    body = " ".join(" ".join(sections).split())
    if not body:
        return None
    return f"{title}. {body}" if title else body


def exclusion_map(details: dict[str, dict]) -> dict[str, set[str]]:
    """Symmetric 'Not applicable together with' links.

    A pair is excluded when either course lists the other, because DTU does not
    always repeat the restriction on both pages.
    """
    excluded: dict[str, set[str]] = {}
    for course, entry in details.items():
        for other in entry.get("not_applicable_with", []):
            if other != course:
                excluded.setdefault(course, set()).add(other)
                excluded.setdefault(other, set()).add(course)
    return excluded


def nearest_neighbours(courses: list[str], vectors, excluded: dict[str, set[str]],
                       top_k: int = DEFAULT_TOP_K) -> dict[str, list[list]]:
    """Top-k most similar courses for each course, skipping excluded pairs.

    `vectors` must be L2-normalised rows aligned with `courses`.
    """
    import numpy as np

    vectors = np.asarray(vectors, dtype=np.float32)
    scores = vectors @ vectors.T
    np.fill_diagonal(scores, -np.inf)
    index = {course: i for i, course in enumerate(courses)}
    for course, others in excluded.items():
        if course in index:
            for other in others:
                if other in index:
                    scores[index[course], index[other]] = -np.inf

    result = {}
    for i, course in enumerate(courses):
        # Stable sort keeps equal scores in course order, so output is deterministic
        order = np.argsort(-scores[i], kind="stable")
        result[course] = [[courses[j], round(float(scores[i, j]), 3)]
                          for j in order[:top_k] if np.isfinite(scores[i, j])]
    return result


def near_duplicates(courses: list[str], vectors, excluded: dict[str, set[str]],
                    threshold: float = 0.95) -> list[tuple[str, str, float]]:
    """Very similar pairs with no exclusion link, for manual review."""
    import numpy as np

    vectors = np.asarray(vectors, dtype=np.float32)
    scores = vectors @ vectors.T
    pairs = []
    for i, j in zip(*np.where(np.triu(scores, k=1) >= threshold)):
        a, b = courses[i], courses[j]
        if b not in excluded.get(a, set()):
            pairs.append((a, b, round(float(scores[i, j]), 3)))
    return sorted(pairs, key=lambda pair: -pair[2])


def embeddinggemma_encoder(model_name: str = DEFAULT_MODEL,
                           batch_size: int = 8) -> Callable[[list[str]], object]:
    """Text-only EmbeddingGemma 2 encoder returning normalised 768d vectors."""
    import torch
    from sentence_transformers import SentenceTransformer

    # The model card warns float16 yields NaN; bfloat16 is not faster on most CPUs
    model = SentenceTransformer(
        model_name,
        config_kwargs={"vision_config": None, "audio_config": None},
        model_kwargs={"torch_dtype": torch.float32},
    )

    def encode(texts: list[str]):
        return model.encode(texts, prompt_name=SIMILARITY_PROMPT, normalize_embeddings=True,
                            batch_size=batch_size, show_progress_bar=True)

    return encode


def build_similarity(data: dict, details: dict, encode: Callable[[Iterable[str]], object],
                     top_k: int = DEFAULT_TOP_K) -> tuple[dict, dict]:
    """Neighbour lists for every course in `data` that has description text.

    Returns (neighbours, diagnostics).
    """
    courses, texts = [], []
    for course in sorted(data):
        text = similarity_text(course_title(data[course]), details.get(course, {}))
        if text:
            courses.append(course)
            texts.append(text)
    excluded = exclusion_map(details)
    vectors = encode(texts) if texts else []
    neighbours = nearest_neighbours(courses, vectors, excluded, top_k) if courses else {}
    diagnostics = {
        "embedded": len(courses),
        "without_description": sorted(set(data) - set(courses)),
        "excluded_pairs": sum(len(v) for v in excluded.values()) // 2,
        "near_duplicates": near_duplicates(courses, vectors, excluded) if courses else [],
    }
    return neighbours, diagnostics
