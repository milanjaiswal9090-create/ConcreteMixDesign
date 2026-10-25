"""Document ingestion pipeline for PDFs, DOCX, and plain text files.

Extracts text, creates searchable chunks while preserving calculation
sequences and table structures.
"""

import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk

logger = logging.getLogger(__name__)


class DocumentIngester:
    """Ingests documents, extracts text, creates searchable chunks."""

    SUPPORTED_TYPES = {".pdf", ".docx", ".doc", ".txt", ".md"}
    MAX_CHUNK_SIZE = 1500   # characters
    CHUNK_OVERLAP = 200     # characters

    def __init__(self, db_session_factory, upload_dir: str = "data/documents") -> None:
        self.db_factory = db_session_factory
        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Main entry
    # ------------------------------------------------------------------

    def ingest_file(
        self,
        filepath: str,
        original_name: str,
        standard_name: str = "",
        edition: str = "",
    ) -> Dict[str, Any]:
        """Ingest a single file. Returns ``{document_id, status, chunks_created, errors}``."""
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in self.SUPPORTED_TYPES:
            return {"document_id": None, "status": "failed",
                    "chunks_created": 0, "errors": [f"Unsupported file type: {ext}"]}

        errors: List[str] = []
        db: Session = self.db_factory()
        try:
            # Check duplicate
            with open(filepath, "rb") as fh:
                content_hash = hashlib.sha256(fh.read()).hexdigest()[:16]
            stored_name = f"{content_hash}_{original_name}"

            existing = db.query(Document).filter(Document.filename == stored_name).first()
            if existing:
                return {"document_id": existing.id, "status": "duplicate",
                        "chunks_created": 0, "errors": ["Document already ingested"]}

            # Extract text
            pages: List[Dict] = []
            if ext == ".pdf":
                pages = self.extract_text_pdf(filepath)
            elif ext in (".docx", ".doc"):
                pages = self.extract_text_docx(filepath)
            elif ext in (".txt", ".md"):
                text = self.extract_text_plain(filepath)
                pages = [{"page": 1, "text": text}]

            if not pages:
                errors.append("No text could be extracted from the document")

            # Create DB record
            doc = Document(
                filename=stored_name,
                original_name=original_name,
                doc_type=ext.lstrip("."),
                standard_name=standard_name,
                edition=edition,
                status="processed" if pages else "failed",
                page_count=len(pages),
                error_message="; ".join(errors) if errors else None,
            )
            db.add(doc)
            db.flush()

            # Chunk and store
            chunks = self.chunk_text(pages)
            for i, chunk in enumerate(chunks):
                db_chunk = DocumentChunk(
                    document_id=doc.id,
                    chunk_text=chunk["text"],
                    chunk_index=i,
                    page_number=chunk.get("page"),
                    section_heading=chunk.get("section"),
                    metadata_json=json.dumps(chunk.get("metadata", {})),
                )
                db.add(db_chunk)

            db.commit()
            return {
                "document_id": doc.id,
                "status": doc.status,
                "chunks_created": len(chunks),
                "errors": errors,
            }
        except Exception as e:
            db.rollback()
            logger.exception("Error ingesting %s", original_name)
            return {"document_id": None, "status": "failed",
                    "chunks_created": 0, "errors": [str(e)]}
        finally:
            db.close()

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------

    def extract_text_pdf(self, filepath: str) -> List[Dict]:
        """Extract text from PDF page by page."""
        pages: List[Dict] = []
        try:
            import pdfplumber
            with pdfplumber.open(filepath) as pdf:
                for i, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    pages.append({"page": i, "text": text})
        except ImportError:
            logger.warning("pdfplumber not installed; PDF extraction unavailable")
            pages.append({"page": 1, "text": "[PDF extraction requires pdfplumber]"})
        except Exception as e:
            logger.exception("PDF extraction failed for %s", filepath)
            pages.append({"page": 1, "text": f"[Extraction error: {e}]"})
        return pages

    def extract_text_docx(self, filepath: str) -> List[Dict]:
        """Extract text from DOCX."""
        pages: List[Dict] = []
        try:
            from docx import Document as DocxDocument
            doc = DocxDocument(filepath)
            full_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
            # Treat each ~2000 chars as a "page" for chunking
            for i in range(0, max(1, len(full_text)), 2000):
                pages.append({"page": i // 2000 + 1, "text": full_text[i:i + 2000]})
        except ImportError:
            logger.warning("python-docx not installed; DOCX extraction unavailable")
            pages.append({"page": 1, "text": "[DOCX extraction requires python-docx]"})
        except Exception as e:
            logger.exception("DOCX extraction failed for %s", filepath)
            pages.append({"page": 1, "text": f"[Extraction error: {e}]"})
        return pages

    @staticmethod
    def extract_text_plain(filepath: str) -> str:
        """Read plain text file."""
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_text(self, pages: List[Dict], preserve_calculations: bool = True) -> List[Dict]:
        """Split extracted pages into meaningful chunks.

        Tries to keep calculation sequences and tables together rather
        than splitting at arbitrary character boundaries.
        """
        chunks: List[Dict] = []

        for page_data in pages:
            page_num = page_data.get("page")
            text = page_data.get("text", "")
            if not text.strip():
                continue

            # Detect section headings
            sections = self._split_by_sections(text)

            for section_heading, section_text in sections:
                # If small enough, keep as one chunk
                if len(section_text) <= self.MAX_CHUNK_SIZE:
                    chunks.append({
                        "text": section_text.strip(),
                        "page": page_num,
                        "section": section_heading,
                        "metadata": {"page": page_num, "section": section_heading},
                    })
                    continue

                # Split at paragraph boundaries
                paragraphs = re.split(r"\n\s*\n", section_text)
                current = ""
                for para in paragraphs:
                    # Don't split calculation blocks
                    if preserve_calculations and self._is_calculation_block(para):
                        if current.strip():
                            chunks.append({
                                "text": current.strip(),
                                "page": page_num,
                                "section": section_heading,
                                "metadata": {"page": page_num, "section": section_heading},
                            })
                            current = ""
                        chunks.append({
                            "text": para.strip(),
                            "page": page_num,
                            "section": section_heading,
                            "metadata": {"page": page_num, "section": section_heading,
                                         "type": "calculation"},
                        })
                        continue

                    if len(current) + len(para) > self.MAX_CHUNK_SIZE:
                        if current.strip():
                            chunks.append({
                                "text": current.strip(),
                                "page": page_num,
                                "section": section_heading,
                                "metadata": {"page": page_num, "section": section_heading},
                            })
                        current = para
                    else:
                        current += "\n\n" + para if current else para

                if current.strip():
                    chunks.append({
                        "text": current.strip(),
                        "page": page_num,
                        "section": section_heading,
                        "metadata": {"page": page_num, "section": section_heading},
                    })

        return chunks

    @staticmethod
    def _split_by_sections(text: str) -> List[tuple]:
        """Split text into (heading, content) pairs."""
        heading_re = re.compile(
            r"^((?:\d+\.)+\s*.+|[A-Z][A-Z\s]{3,}|Table\s+\d+|Clause\s+\d+)",
            re.MULTILINE,
        )
        parts = heading_re.split(text)
        sections = []
        current_heading = ""
        for i, part in enumerate(parts):
            if heading_re.match(part.strip()):
                current_heading = part.strip()
            else:
                if part.strip():
                    sections.append((current_heading, part))
        if not sections and text.strip():
            sections = [("", text)]
        return sections

    @staticmethod
    def _is_calculation_block(text: str) -> bool:
        """Detect text that looks like a calculation sequence."""
        calc_indicators = [
            r"=\s*[\d.]+",
            r"step\s*\d",
            r"f['']?ck\s*=",
            r"w/c\s*=",
            r"kg/m[³3]",
            r"N/mm[²2]",
        ]
        count = sum(1 for pat in calc_indicators if re.search(pat, text, re.I))
        return count >= 2

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_ingestion_status(self) -> Dict[str, Any]:
        """Get overall ingestion statistics."""
        db: Session = self.db_factory()
        try:
            total_docs = db.query(Document).count()
            processed = db.query(Document).filter(Document.status == "processed").count()
            failed = db.query(Document).filter(Document.status == "failed").count()
            total_chunks = db.query(DocumentChunk).count()
            return {
                "total_documents": total_docs,
                "processed": processed,
                "failed": failed,
                "total_chunks": total_chunks,
            }
        finally:
            db.close()
