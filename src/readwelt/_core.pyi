from pathlib import Path

class ParagraphAnchor:
    @property
    def anchor_id(self) -> str: ...
    @property
    def ordinal(self) -> int: ...
    @property
    def start_byte(self) -> int: ...
    @property
    def end_byte(self) -> int: ...
    @property
    def start_char(self) -> int: ...
    @property
    def end_char(self) -> int: ...
    @property
    def text(self) -> str: ...

class PreparedText:
    @property
    def text(self) -> str: ...
    @property
    def digest(self) -> str: ...
    @property
    def paragraphs(self) -> list[ParagraphAnchor]: ...

class StoredObject:
    @property
    def digest(self) -> str: ...
    @property
    def relative_path(self) -> str: ...
    @property
    def size(self) -> int: ...
    @property
    def created(self) -> bool: ...

class RetrievalIndex:
    def __init__(
        self,
        documents: list[list[str]],
        scorer: str = ...,
        k1: float = ...,
        b: float = ...,
        delta: float = ...,
    ) -> None: ...
    @property
    def document_count(self) -> int: ...
    @property
    def vocabulary_size(self) -> int: ...
    def rank(
        self,
        query: list[str],
        top_k: int | None = ...,
    ) -> list[tuple[int, float]]: ...

class DenseIndex:
    def __init__(
        self,
        documents: list[list[float]],
        dimensions: int,
    ) -> None: ...
    @property
    def document_count(self) -> int: ...
    def rank(
        self,
        queries: list[list[float]],
    ) -> tuple[list[float], list[tuple[int, float]]]: ...

def prepare(text: str) -> PreparedText: ...
def put_object(object_root: Path, data: bytes) -> StoredObject: ...
def semantic_analyze(
    texts: list[str], near_duplicate_threshold: float
) -> list[
    tuple[
        list[str],
        int,
        int,
        int,
        int,
        str,
        int | None,
        list[int],
    ]
]: ...
def bm25_rank(
    documents: list[list[str]],
    query: list[str],
    k1: float = ...,
    b: float = ...,
) -> list[tuple[int, float]]: ...
def cosine_scores(
    query: list[float],
    document_vectors: list[float],
    dimensions: int,
) -> list[float]: ...
def hybrid_rrf(
    document_count: int,
    lexical_ranking: list[tuple[int, float]],
    dense_scores: list[float],
    top_k: int,
    fusion: tuple[float, float, float] = ...,
) -> list[tuple[int, float]]: ...
def select_evidence(
    scores: list[float],
    section_ordinals: list[int],
    priority_flags: list[bool],
    token_costs: list[int],
    token_budget: int,
) -> tuple[list[int], list[int], int]: ...
def coverage_intervals(
    text: str, ranges: list[tuple[int, int]]
) -> tuple[list[tuple[int, int]], int]: ...
