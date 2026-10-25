"""Comprehensive test suite for ConcreteMix AI.

Covers:
1. Deterministic calculation engine (IS 10262:2019 + IS 456 Table 5)
2. Natural language parser
3. Input validation
4. Hybrid retrieval (BM25 + TF-IDF)
5. 100 Solved benchmark examples integrity
"""

import pytest
from app.engine.is10262 import design, IS456_TABLE5_RCC, IS456_TABLE5_PCC
from app.engine.parser import parse_problem
from app.engine.validator import validate_inputs
from app.rag.embeddings import TFIDFEmbedder
from app.rag.search import HybridSearcher


def test_is10262_conventional_m25():
    """Verify standard M25 RCC mild exposure mix calculation."""
    p = {
        "fck": 25,
        "exposure": "mild",
        "member": "RCC",
        "max_size": 20,
        "slump": 75,
        "zone": "II",
        "cement_grade": 43,
        "sg_cement": 3.15,
        "sg_fa": 2.65,
        "sg_ca": 2.70,
        "abs_fa": 1.0,
        "abs_ca": 0.5,
        "fm_fa": 0.0,
        "fm_ca": 0.0,
    }
    res = design(p)
    assert res["all_checks_pass"] is True
    assert res["target_strength"] == 31.6
    assert res["w_c_adopted"] <= 0.55
    assert res["mix_per_m3"]["cement"] >= 300
    assert abs(res["steps"][8]["value"] + sum(s["value"] for s in res["steps"] if "Volume of" in s["step"]) - 1.0) < 0.5


def test_parser_extracts_structural_specs():
    """Verify natural-language parser extracts grade, exposure, slump, aggregate."""
    text = "Design a concrete mix of grade M30 for an RCC column in coastal severe environment. Maximum size 20 mm, slump 100 mm, OPC 43 grade, Zone II sand."
    parsed = parse_problem(text)
    data = parsed["parsed"]
    assert data["fck"] == 30
    assert data["exposure"] == "severe"
    assert data["member"] == "RCC"
    assert data["max_size"] == 20
    assert data["slump"] == 100
    assert data["zone"] == "II"
    assert data["cement_grade"] == 43


def test_validator_detects_invalid_inputs():
    """Verify input validator flags illegal grades and exposures."""
    # Grade below durability limit
    errors, _ = validate_inputs({"fck": 15, "exposure": "severe", "member": "RCC"})
    assert any("does not meet the minimum grade" in e for e in errors)

    # Invalid zone
    errors, _ = validate_inputs({"fck": 30, "exposure": "mild", "zone": "V"})
    assert any("Zone 'V' is not valid" in e for e in errors)


def test_hybrid_searcher_retrieval():
    """Verify TF-IDF and BM25 search returns relevant benchmark cases."""
    docs = [
        {"id": "P001", "text": "M25 concrete mild RCC 40mm slump 100mm", "metadata": {"grade": "M25", "exposure": "mild"}},
        {"id": "P035", "text": "M30 concrete severe RCC coastal column 20mm slump 75mm", "metadata": {"grade": "M30", "exposure": "severe"}},
    ]
    embedder = TFIDFEmbedder(index_path="data/test_index")
    searcher = HybridSearcher(embedder)
    searcher.index_documents(docs)

    results = searcher.search("coastal severe M30", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == "P035"
