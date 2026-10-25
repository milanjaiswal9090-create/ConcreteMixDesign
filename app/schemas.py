"""
Pydantic request/response schemas for ConcreteMix AI API.

Defines typed models for mix design requests, responses,
example records, search, and document management.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────── SCM & Admixture ────────────────────────

class SCMInput(BaseModel):
    """Supplementary cementitious material input."""
    type: str = Field(..., description="SCM type: FA, GGBS, or SF")
    percent: float = Field(..., ge=0, le=70, description="Percent of total cementitious")


# ──────────────────────────────────── Mix Design ─────────────────────────────

class MixDesignRequest(BaseModel):
    """
    Request body for a concrete mix design calculation.

    Supports both natural-language problem statements and structured inputs.
    If problem_text is provided, the parser will extract structured parameters.
    """
    problem_text: Optional[str] = Field(
        None, description="Natural language problem statement"
    )
    # Structured inputs (override parsed values if both provided)
    fck: Optional[float] = Field(None, ge=10, le=80, description="Characteristic compressive strength (N/mm²)")
    exposure: Optional[str] = Field(None, description="Exposure condition")
    member: Optional[str] = Field("RCC", description="Member type: RCC or PCC")
    max_size: Optional[int] = Field(None, description="Maximum nominal aggregate size in mm")
    slump: Optional[int] = Field(None, description="Slump in mm")
    zone: Optional[str] = Field(None, description="Fine aggregate zone: I, II, III, or IV")
    cement_grade: Optional[int] = Field(None, description="Cement grade: 33, 43, or 53")
    sg_cement: Optional[float] = Field(None, ge=2.0, le=3.5, description="Specific gravity of cement")
    sg_fa: Optional[float] = Field(None, ge=2.0, le=3.5, description="Specific gravity of fine aggregate")
    sg_ca: Optional[float] = Field(None, ge=2.0, le=3.5, description="Specific gravity of coarse aggregate")
    abs_fa: Optional[float] = Field(None, ge=0, le=10, description="Water absorption of FA (%)")
    abs_ca: Optional[float] = Field(None, ge=0, le=10, description="Water absorption of CA (%)")
    fm_fa: Optional[float] = Field(None, description="Free moisture in FA (%)")
    fm_ca: Optional[float] = Field(None, description="Free moisture in CA (%)")
    scm: Optional[list[SCMInput]] = Field(None, description="SCM additions")
    sp_pct: Optional[float] = Field(None, ge=0, le=5, description="Superplasticiser % by mass of cementitious")
    sp_wr: Optional[float] = Field(None, ge=0, le=0.5, description="Water reduction fraction from SP")
    pumped: Optional[bool] = Field(False, description="Whether concrete is to be pumped")


class MixQuantities(BaseModel):
    """Computed mix quantities per cubic metre."""
    cement: float
    scm: dict[str, float] = {}
    water: float
    fine_aggregate_ssd: float
    coarse_aggregate_ssd: float
    admixture: float
    cementitious_total: float
    w_cm: float
    ratio_by_mass_cementitious: str
    field_adjusted: dict[str, float] = {}


class DesignStep(BaseModel):
    """A single step in the mix design computation."""
    step: str
    clause: str
    value: Any
    note: str = ""


class MixDesignResult(BaseModel):
    """Full result from the IS 10262 design calculation."""
    target_strength: float
    w_c_adopted: float
    predicted_28d_mean: float
    mix_per_m3: MixQuantities
    steps: list[DesignStep]
    checks: dict[str, bool]
    all_checks_pass: bool


class MixDesignResponse(BaseModel):
    """Complete response for a mix design request."""
    session_id: str
    parsed_inputs: dict[str, Any]
    assumptions: list[str] = []
    missing_fields: list[str] = []
    warnings: list[str] = []
    result: MixDesignResult
    retrieved_examples: list[ExampleSummary] = []


# ──────────────────────────────────── Examples ───────────────────────────────

class ExampleSummary(BaseModel):
    """Brief summary of a solved example for listing."""
    id: int
    external_id: str
    group: Optional[str] = None
    grade: Optional[str] = None
    exposure: Optional[str] = None
    member: Optional[str] = None
    max_size: Optional[int] = None
    slump: Optional[int] = None
    zone: Optional[str] = None
    cement_grade: Optional[int] = None
    verification_status: str = "unverified"
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ExampleDetail(BaseModel):
    """Full detail of a solved example including inputs and solution."""
    id: int
    external_id: str
    group: Optional[str] = None
    grade: Optional[str] = None
    exposure: Optional[str] = None
    member: Optional[str] = None
    max_size: Optional[int] = None
    slump: Optional[int] = None
    zone: Optional[str] = None
    cement_grade: Optional[int] = None
    problem_statement: Optional[str] = None
    inputs_json: Optional[Any] = None
    solution_json: Optional[Any] = None
    mix_json: Optional[Any] = None
    checks_json: Optional[Any] = None
    verification_status: str = "unverified"
    source: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────── Search ─────────────────────────────────

class SearchRequest(BaseModel):
    """Search query for hybrid BM25 + TF-IDF retrieval."""
    query: str = Field(..., min_length=3, description="Search query text")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    search_examples: bool = Field(True, description="Search in examples")
    search_documents: bool = Field(True, description="Search in document chunks")


class SearchResult(BaseModel):
    """A single search result item."""
    source_type: str  # "example" or "document_chunk"
    source_id: int
    title: str
    snippet: str
    score: float
    metadata: dict[str, Any] = {}


class SearchResponse(BaseModel):
    """Aggregated search results."""
    query: str
    total_results: int
    results: list[SearchResult]


# ──────────────────────────────────── Documents ──────────────────────────────

class DocumentUpload(BaseModel):
    """Metadata for a document upload."""
    standard_name: Optional[str] = None
    edition: Optional[str] = None


class DocumentStatus(BaseModel):
    """Status of an uploaded document."""
    id: int
    filename: str
    original_name: str
    doc_type: str
    standard_name: Optional[str] = None
    edition: Optional[str] = None
    status: str
    page_count: Optional[int] = None
    error_message: Optional[str] = None
    chunk_count: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DocumentChunkDetail(BaseModel):
    """Detail of a single document chunk."""
    id: int
    chunk_index: int
    chunk_text: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────── Admin ───────────────────────────────────

class SystemStatus(BaseModel):
    """System health and statistics."""
    app_name: str
    version: str
    total_examples: int
    total_documents: int
    total_chunks: int
    total_sessions: int
    database_size_mb: float


class ImportResult(BaseModel):
    """Result of a bulk import operation."""
    imported: int
    skipped: int
    errors: list[str]


# Forward reference update (MixDesignResponse references ExampleSummary)
MixDesignResponse.model_rebuild()
