from pydantic import BaseModel, Field
from typing import Optional


class LibrarySearchParams(BaseModel):
    q: str = Field(..., min_length=1)
    collection: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="search_with_ai", pattern="^(search_only|search_with_ai)$")


class LibraryQueryRequest(BaseModel):
    query: str = Field(..., min_length=1)
    collection: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="search_with_ai", pattern="^(search_only|search_with_ai)$")


class SourceInfo(BaseModel):
    book: str = ""
    chapter: str = ""
    section: str = ""
    page: str = ""
    text: str = ""
    score: float = 0.0
    collection: str = ""


class LibrarySearchResponse(BaseModel):
    query: str
    collection: Optional[str] = None
    mode: str
    intent: Optional[str] = None
    answer: Optional[str] = None
    references: list[str] = []
    follow_up_questions: list[str] = []
    sources: list[SourceInfo] = []


class LibraryCollectionInfo(BaseModel):
    name: str
    chunk_count: int


class LibrarySourcesResponse(BaseModel):
    collections: list[LibraryCollectionInfo]


class BookInfo(BaseModel):
    name: str
    collection: str
    path: str


class LibraryBooksResponse(BaseModel):
    books: list[BookInfo]


class TopicInfo(BaseModel):
    name: str
    count: int
    collections: list[str]


class LibraryTopicsResponse(BaseModel):
    topics: list[TopicInfo]
