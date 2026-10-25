"""Mix design API — the core endpoint that runs the IS 10262 calculation."""

import json
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.engine.is10262 import design as is10262_design
from app.engine.parser import parse_problem
from app.engine.validator import validate_inputs
from app.models import DesignSession
from app.rag.examples import ExampleManager
from app.database import SessionLocal

router = APIRouter(prefix="/api/design", tags=["design"])


def _get_example_manager() -> ExampleManager:
    return ExampleManager(SessionLocal)


@router.post("/parse")
def parse_only(request: Dict[str, Any]):
    """Endpoint for live front-end problem statement parsing.
    Returns extracted facts, assumptions, and suggested parameters in real-time.
    """
    text = request.get("problem_text", "")
    return parse_problem(text)


@router.post("")
def create_design(request: Dict[str, Any], db: Session = Depends(get_db)):
    """Run a concrete mix design calculation.

    Accepts either a ``problem_text`` (natural language) or structured
    inputs.  Returns parsed inputs, assumptions, calculation result,
    and similar solved examples.
    """
    problem_text = request.get("problem_text", "")
    structured = {k: v for k, v in request.items() if k != "problem_text" and v is not None and v != ""}

    # ── Step 1: Parse natural language if provided ───────────────────────
    parsed_result = {"parsed": {}, "facts": [], "assumptions": [], "missing": [], "warnings": []}
    if problem_text:
        parsed_result = parse_problem(problem_text)

    # Merge: structured inputs explicitly override parsed values
    inputs = {**parsed_result["parsed"], **structured}

    # Handle SCM format from frontend
    if "scm" in inputs and inputs["scm"]:
        scm_list = []
        for item in inputs["scm"]:
            if isinstance(item, dict):
                scm_list.append((item["type"], item["percent"]))
            elif isinstance(item, (list, tuple)):
                scm_list.append(tuple(item))
        inputs["scm"] = scm_list

    # ── Step 2: Validate ─────────────────────────────────────────────────
    errors, warnings = validate_inputs(inputs)
    if errors:
        raise HTTPException(status_code=422, detail={
            "message": "Validation failed",
            "errors": errors,
            "warnings": warnings,
            "parsed_inputs": inputs,
            "facts": parsed_result["facts"],
            "assumptions": parsed_result["assumptions"],
            "missing": parsed_result["missing"],
        })

    all_warnings = parsed_result["warnings"] + warnings

    # ── Step 3: Check for missing required inputs ────────────────────────
    required = ["fck", "exposure"]
    still_missing = [f for f in required if f not in inputs or inputs[f] is None]
    if still_missing:
        raise HTTPException(status_code=422, detail={
            "message": "Missing required inputs",
            "errors": [f"'{f}' is required" for f in still_missing],
            "parsed_inputs": inputs,
            "facts": parsed_result["facts"],
            "assumptions": parsed_result["assumptions"],
            "missing": parsed_result["missing"],
        })

    # ── Step 4: Set defaults for optional inputs ─────────────────────────
    defaults = {
        "max_size": 20, "slump": 75, "zone": "II", "cement_grade": 43,
        "sg_cement": 3.15, "sg_fa": 2.65, "sg_ca": 2.70,
        "abs_fa": 1.0, "abs_ca": 0.5, "fm_fa": 0.0, "fm_ca": 0.0,
        "pumped": False,
    }
    assumptions = list(parsed_result["assumptions"])
    for k, v in defaults.items():
        if k not in inputs or inputs[k] is None:
            inputs[k] = v
            assumptions.append({"field": k, "value": v, "reason": f"Not specified; using default {v}"})

    # For high grade mixes (M55+), set advanced=True in design
    if inputs.get("fck", 0) >= 55:
        inputs["advanced"] = True

    # ── Step 5: Run calculation ──────────────────────────────────────────
    try:
        result = is10262_design(inputs)
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "message": f"Calculation engine error: {e}",
            "parsed_inputs": inputs,
        })

    # ── Step 6: Retrieve similar examples ────────────────────────────────
    mgr = _get_example_manager()
    similar = mgr.get_similar_examples(inputs, top_k=3)

    # ── Step 7: Save session ─────────────────────────────────────────────
    session_id = str(uuid.uuid4())
    session = DesignSession(
        session_id=session_id,
        problem_text=problem_text,
        parsed_inputs_json=json.dumps(inputs, ensure_ascii=False, default=str),
        result_json=json.dumps(result, ensure_ascii=False, default=str),
        retrieved_examples_json=json.dumps(
            [{"external_id": s["external_id"], "similarity": s.get("similarity_score", 0)}
             for s in similar],
            ensure_ascii=False,
        ),
    )
    db.add(session)
    db.commit()

    # ── Build response ───────────────────────────────────────────────────
    return {
        "session_id": session_id,
        "parsed_inputs": inputs,
        "facts": parsed_result["facts"],
        "assumptions": assumptions,
        "missing": parsed_result["missing"],
        "warnings": all_warnings,
        "result": result,
        "retrieved_examples": similar,
    }


@router.get("/{session_id}")
def get_design_session(session_id: str, db: Session = Depends(get_db)):
    """Retrieve a previously saved design session."""
    session = db.query(DesignSession).filter(DesignSession.session_id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session.session_id,
        "problem_text": session.problem_text,
        "parsed_inputs": json.loads(session.parsed_inputs_json or "{}"),
        "result": json.loads(session.result_json or "{}"),
        "retrieved_examples": json.loads(session.retrieved_examples_json or "[]"),
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }
