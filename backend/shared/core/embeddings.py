from functools import lru_cache
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = structlog.get_logger()

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


@lru_cache(maxsize=1)
def _get_model() -> "SentenceTransformer":
    """Load model once and cache — takes ~2s on first call."""
    from sentence_transformers import SentenceTransformer

    log.info("embeddings.loading_model", model=MODEL_NAME)
    model = SentenceTransformer(MODEL_NAME)
    log.info("embeddings.model_loaded")
    return model


def embed_text(text: str) -> list[float]:
    """Embed a single text string. Returns 384-dim vector."""
    model = _get_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. ~50ms per batch of 32."""
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return [v.tolist() for v in vectors]
