# ConcreteMix AI — IS 10262:2019 Concrete Mix Design Platform

**ConcreteMix AI** is a production-oriented, code-compliant civil engineering platform for concrete mix proportioning and code verification.

Tagline: *From design requirements to code-verified concrete mix proportions.*

---

## Features
- **100% Deterministic Engine**: Implements the mathematical proportioning procedure of **IS 10262:2019** and durability limits of **IS 456:2000 (Table 5)** with zero runtime LLM dependency.
- **Natural Language Parsing**: Deterministic regex extraction of concrete grade, exposure, workability/slump, aggregate nominal size, fine aggregate grading zone, and SCMs.
- **100 Solved Problems Knowledge Base**: Complete benchmark dataset spanning:
  - Group A: Conventional Mixes (30 problems)
  - Group B: Exposure & Durability (15 problems)
  - Group C: Pumped Concrete Workability (15 problems)
  - Group D: Fly Ash & GGBS Blends (15 problems)
  - Group E: Aggregate Zones I-IV & Varied SGs (15 problems)
  - Group F: High-Strength M55-M70 & Self-Compacting Concrete (10 problems)
- **Hybrid Retrieval (RAG)**: BM25 keyword matching combined with offline TF-IDF cosine semantic search and structural metadata filtering.
- **Yield & Durability Auditing**: 8 boundary checks verified for every single proportioning run (Absolute volume sums to 1.0 m³, w/cm bounds, minimum binder limits, max cement checks).
- **SEO & Performance Ready**: Server-rendered Jinja2 layouts with Tailwind CSS, clean semantic HTML, sitemap.xml, robots.txt, and educational guide routes.

---

## Directory Structure
```
concretemix-ai/
├── app/
│   ├── config.py             # App settings (Pydantic)
│   ├── database.py           # SQLite + SQLAlchemy synchronous engine
│   ├── models.py             # ORM models (Example, Document, DocumentChunk, DesignSession)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── main.py               # FastAPI entrypoint, template routes & SEO
│   ├── engine/
│   │   ├── is10262.py        # Preserved deterministic IS 10262:2019 calculation engine
│   │   ├── parser.py         # Natural-language problem statement parser
│   │   └── validator.py      # Input validation & cross-field durability boundary checks
│   ├── rag/
│   │   ├── embeddings.py     # Offline TF-IDF vectorizer & cosine similarity indexer
│   │   ├── search.py         # Hybrid BM25 + TF-IDF searcher with metadata filtering
│   │   ├── examples.py       # 100 Solved benchmark examples manager & similarity ranker
│   │   └── ingestion.py      # Document chunking & PDF/DOCX text extraction pipeline
│   ├── api/
│   │   ├── design.py         # POST /api/design calculation endpoint
│   │   ├── examples.py       # GET /api/examples & /api/examples/{id}
│   │   ├── search.py         # GET /api/search hybrid query endpoint
│   │   ├── documents.py      # PDF upload & inspection endpoints
│   │   └── admin.py          # Admin re-indexing & database statistics
│   ├── templates/            # High-end Jinja2 templates (Inter + Tailwind CSS)
│   │   ├── base.html
│   │   ├── index.html        # Landing page
│   │   ├── design.html       # 7-Step Mix Design Workbench
│   │   ├── library.html      # 100 Solved Problems Knowledge Library
│   │   ├── example_detail.html # Deep-dive problem solution & audit
│   │   ├── methodology.html  # Technical calculation methodology
│   │   ├── docs.html         # Documentation & FAQ
│   │   ├── admin.html        # Protected ingestion management
│   │   └── seo/              # Educational SEO pages
│   └── static/
├── data/
│   ├── concretemix.db        # SQLite database (100 problems imported)
│   ├── tfidf_index/          # Persisted TF-IDF vocabulary, doc matrix & IDF weights
│   └── examples/             # Raw JSONL and summary CSV datasets
├── tests/
│   └── test_engine.py        # Pytest test suite
└── requirements.txt
```

---

## Quickstart

### 1. Requirements
- Python 3.10+ (tested on Python 3.13)

### 2. Run the Platform
Navigate to the project root and launch Uvicorn:
```bash
cd concretemix-ai
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser at:
- **Application Overview**: [http://localhost:8000](http://localhost:8000)
- **Mix Design Workbench**: [http://localhost:8000/design](http://localhost:8000/design)
- **100 Solved Problems Library**: [http://localhost:8000/library](http://localhost:8000/library)
- **Interactive OpenAPI Docs**: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)

### 3. Run the Automated Tests
```bash
python -m pytest tests -v
```
All 4 test suites will run and verify calculations, parsing, boundaries, and retrieval.
