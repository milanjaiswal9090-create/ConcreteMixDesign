"""Import and manage the 100 solved mix design examples.

Handles JSONL ingestion, validation, similarity search, and CRUD
operations against the SQLite database.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import Example

logger = logging.getLogger(__name__)


class ExampleManager:
    """Manages import, validation, and retrieval of solved examples."""

    def __init__(self, db_session_factory) -> None:
        self.db_factory = db_session_factory

    # ------------------------------------------------------------------
    # Import
    # ------------------------------------------------------------------

    def import_from_jsonl(self, filepath: str) -> Dict[str, Any]:
        """Import examples from a JSONL file.

        Returns ``{imported, skipped, errors}`` summary.
        """
        imported = 0
        skipped = 0
        errors: List[str] = []

        db: Session = self.db_factory()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line_no, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as e:
                        errors.append(f"Line {line_no}: JSON parse error – {e}")
                        continue

                    valid, issues = self.validate_example(data)
                    if not valid:
                        errors.append(f"Line {line_no} ({data.get('id', '?')}): {'; '.join(issues)}")
                        continue

                    ext_id = data["id"]
                    existing = db.query(Example).filter(Example.external_id == ext_id).first()
                    if existing:
                        skipped += 1
                        continue

                    inputs = data.get("inputs", {})
                    ex = Example(
                        external_id=ext_id,
                        group=data.get("group"),
                        grade=f"M{inputs.get('fck', '')}",
                        exposure=inputs.get("exposure"),
                        member=inputs.get("member", "RCC"),
                        max_size=inputs.get("max_size"),
                        slump=inputs.get("slump"),
                        zone=inputs.get("zone"),
                        cement_grade=inputs.get("cement_grade"),
                        problem_statement=data.get("problem_statement"),
                        inputs_json=json.dumps(inputs, ensure_ascii=False),
                        solution_json=json.dumps(data.get("solution_steps", []), ensure_ascii=False),
                        mix_json=json.dumps(data.get("mix_per_m3", {}), ensure_ascii=False),
                        checks_json=json.dumps(data.get("checks", {}), ensure_ascii=False),
                        retrieval_text=data.get("retrieval_text", ""),
                        verification_status=data.get("verification_status", "unverified"),
                        source=data.get("source", ""),
                    )
                    db.add(ex)
                    imported += 1

            db.commit()
        except Exception as e:
            db.rollback()
            errors.append(f"Database error: {e}")
            logger.exception("Error during JSONL import")
        finally:
            db.close()

        return {"imported": imported, "skipped": skipped, "errors": errors}

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_example(data: Dict) -> Tuple[bool, List[str]]:
        """Validate a single example record.

        Returns ``(is_valid, issues_list)``.
        """
        issues: List[str] = []

        if "id" not in data:
            issues.append("Missing required field 'id'")
        if "inputs" not in data:
            issues.append("Missing required field 'inputs'")

        inputs = data.get("inputs", {})
        fck = inputs.get("fck")
        if fck is not None and (fck < 10 or fck > 100):
            issues.append(f"fck={fck} is outside plausible range")

        exposure = inputs.get("exposure")
        if exposure and exposure not in {"mild", "moderate", "severe", "very severe", "extreme"}:
            issues.append(f"Unknown exposure '{exposure}'")

        checks = data.get("checks", {})
        if checks and not all(checks.values()):
            failed = [k for k, v in checks.items() if not v]
            issues.append(f"Failed checks: {', '.join(failed)}")

        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def get_example(self, example_id: str) -> Optional[Dict]:
        """Get a single example by external ID (e.g. 'P001')."""
        db: Session = self.db_factory()
        try:
            ex = db.query(Example).filter(Example.external_id == example_id).first()
            if not ex:
                return None
            return self._to_dict(ex)
        finally:
            db.close()

    def list_examples(
        self,
        grade: Optional[str] = None,
        exposure: Optional[str] = None,
        zone: Optional[str] = None,
        group: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Dict], int]:
        """List examples with optional filtering. Returns (results, total_count)."""
        db: Session = self.db_factory()
        try:
            q = db.query(Example)
            if grade:
                q = q.filter(Example.grade == grade)
            if exposure:
                q = q.filter(Example.exposure == exposure)
            if zone:
                q = q.filter(Example.zone == zone)
            if group:
                q = q.filter(Example.group == group)

            total = q.count()
            examples = q.order_by(Example.external_id).offset(offset).limit(limit).all()
            return [self._to_dict(ex) for ex in examples], total
        finally:
            db.close()

    def get_similar_examples(self, inputs: Dict, top_k: int = 3) -> List[Dict]:
        """Find examples most similar to given inputs.

        Uses a weighted scoring system comparing key parameters.
        """
        db: Session = self.db_factory()
        try:
            all_examples = db.query(Example).all()
            if not all_examples:
                return []

            scored: List[Tuple[float, Dict, Dict]] = []
            target_fck = inputs.get("fck")
            target_exp = inputs.get("exposure")
            target_zone = inputs.get("zone")
            target_size = inputs.get("max_size")
            target_cg = inputs.get("cement_grade")
            target_scm = inputs.get("scm", [])

            for ex in all_examples:
                score = 0.0
                diffs: Dict[str, str] = {}
                matches: List[str] = []

                # Grade similarity (weight: 0.30)
                if target_fck and ex.grade:
                    ex_fck = int(ex.grade.replace("M", ""))
                    if ex_fck == target_fck:
                        score += 0.30
                        matches.append(f"Grade {ex.grade}")
                    elif abs(ex_fck - target_fck) <= 5:
                        score += 0.15
                        diffs["grade"] = f"Target M{target_fck}, example {ex.grade}"
                    else:
                        diffs["grade"] = f"Target M{target_fck}, example {ex.grade}"

                # Exposure (weight: 0.25)
                if target_exp and ex.exposure:
                    if ex.exposure == target_exp:
                        score += 0.25
                        matches.append(f"Exposure: {ex.exposure}")
                    else:
                        diffs["exposure"] = f"Target {target_exp}, example {ex.exposure}"

                # Zone (weight: 0.15)
                zone_order = {"I": 1, "II": 2, "III": 3, "IV": 4}
                if target_zone and ex.zone:
                    if ex.zone == target_zone:
                        score += 0.15
                        matches.append(f"Zone {ex.zone}")
                    elif abs(zone_order.get(ex.zone, 0) - zone_order.get(target_zone, 0)) == 1:
                        score += 0.07
                        diffs["zone"] = f"Target Zone {target_zone}, example Zone {ex.zone}"
                    else:
                        diffs["zone"] = f"Target Zone {target_zone}, example Zone {ex.zone}"

                # Aggregate size (weight: 0.15)
                if target_size and ex.max_size:
                    if ex.max_size == target_size:
                        score += 0.15
                        matches.append(f"Aggregate size: {ex.max_size} mm")
                    else:
                        score += 0.05
                        diffs["max_size"] = f"Target {target_size} mm, example {ex.max_size} mm"

                # Cement grade (weight: 0.10)
                if target_cg and ex.cement_grade:
                    if ex.cement_grade == target_cg:
                        score += 0.10
                        matches.append(f"Cement grade: {ex.cement_grade}")
                    else:
                        score += 0.03
                        diffs["cement_grade"] = f"Target {target_cg}, example {ex.cement_grade}"

                # SCM type (weight: 0.05)
                if target_scm:
                    ex_inputs = json.loads(ex.inputs_json) if ex.inputs_json else {}
                    ex_scm = ex_inputs.get("scm", [])
                    target_types = {s[0] if isinstance(s, (list, tuple)) else s.get("type", "") for s in target_scm}
                    ex_types = {s[0] if isinstance(s, (list, tuple)) else "" for s in ex_scm} if ex_scm else set()
                    if target_types & ex_types:
                        score += 0.05
                        matches.append(f"SCM: {', '.join(target_types & ex_types)}")

                d = self._to_dict(ex)
                d["similarity_score"] = round(score, 3)
                d["matches"] = matches
                d["differences"] = diffs
                scored.append((score, d, diffs))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [item[1] for item in scored[:top_k]]
        finally:
            db.close()

    def update_verification_status(self, example_id: str, status: str, notes: str = "") -> bool:
        """Update verification status of an example."""
        db: Session = self.db_factory()
        try:
            ex = db.query(Example).filter(Example.external_id == example_id).first()
            if not ex:
                return False
            ex.verification_status = status
            if notes:
                ex.source = (ex.source or "") + f" | Note: {notes}"
            db.commit()
            return True
        finally:
            db.close()

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the example collection."""
        db: Session = self.db_factory()
        try:
            total = db.query(Example).count()
            by_group = {}
            for ex in db.query(Example.group).distinct():
                cnt = db.query(Example).filter(Example.group == ex[0]).count()
                by_group[ex[0] or "ungrouped"] = cnt
            by_grade = {}
            for ex in db.query(Example.grade).distinct():
                cnt = db.query(Example).filter(Example.grade == ex[0]).count()
                by_grade[ex[0] or "unknown"] = cnt
            by_status = {}
            for ex in db.query(Example.verification_status).distinct():
                cnt = db.query(Example).filter(Example.verification_status == ex[0]).count()
                by_status[ex[0] or "unknown"] = cnt
            return {
                "total": total,
                "by_group": by_group,
                "by_grade": by_grade,
                "by_verification_status": by_status,
            }
        finally:
            db.close()

    def get_for_search_index(self) -> List[Dict]:
        """Get all examples formatted for the search index."""
        db: Session = self.db_factory()
        try:
            examples = db.query(Example).all()
            docs = []
            for ex in examples:
                docs.append({
                    "id": ex.external_id,
                    "text": ex.retrieval_text or ex.problem_statement or "",
                    "metadata": {
                        "grade": ex.grade,
                        "exposure": ex.exposure,
                        "zone": ex.zone,
                        "max_size": ex.max_size,
                        "member": ex.member,
                        "group": ex.group,
                        "cement_grade": ex.cement_grade,
                        "source_type": "example",
                    },
                })
            return docs
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(ex: Example) -> Dict[str, Any]:
        """Convert an Example ORM object to a plain dict."""
        return {
            "id": ex.id,
            "external_id": ex.external_id,
            "group": ex.group,
            "grade": ex.grade,
            "exposure": ex.exposure,
            "member": ex.member,
            "max_size": ex.max_size,
            "slump": ex.slump,
            "zone": ex.zone,
            "cement_grade": ex.cement_grade,
            "problem_statement": ex.problem_statement,
            "inputs": json.loads(ex.inputs_json) if ex.inputs_json else {},
            "solution_steps": json.loads(ex.solution_json) if ex.solution_json else [],
            "mix_per_m3": json.loads(ex.mix_json) if ex.mix_json else {},
            "checks": json.loads(ex.checks_json) if ex.checks_json else {},
            "retrieval_text": ex.retrieval_text,
            "verification_status": ex.verification_status,
            "source": ex.source,
            "created_at": ex.created_at.isoformat() if ex.created_at else None,
        }


def ingest_initial_examples() -> Dict[str, Any]:
    """Helper to initialize database tables and ingest bundled 100 benchmark examples."""
    import os
    from app.config import settings
    from app.database import init_db, SessionLocal
    from app.rag.embeddings import TFIDFEmbedder
    from app.rag.search import HybridSearcher

    init_db()
    mgr = ExampleManager(SessionLocal)
    jsonl_path = os.path.join(settings.DATA_DIR, "examples", "mix_problems.jsonl")
    result = {"imported": 0, "status": "already_indexed"}

    if os.path.exists(jsonl_path):
        result = mgr.import_from_jsonl(jsonl_path)
        docs = mgr.get_for_search_index()
        if docs:
            embedder = TFIDFEmbedder()
            searcher = HybridSearcher(embedder)
            searcher.index_documents(docs)
            embedder.save_index()
    return result

