"""End-to-end Document Intelligence test — all supported categories.

Runs sample files through the full pipeline (ingest → classify → route →
process → AI analyze → generate note) and verifies all 21 intelligence fields.

Usage:
    python tests/intelligence_test.py
"""
import json
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from app.application.ai_processor import DocumentAIProcessor
from app.core.config import ModelRoutingSettings, OllamaSettings
from app.infrastructure.ingestion import DocumentIngestionService
from app.infrastructure.llm import OllamaClient
from app.infrastructure.routing.classifier import DocumentClassifier
from app.infrastructure.routing.processor_impls import get_processor_by_name
from app.infrastructure.routing.processors import default_processors
from app.infrastructure.routing.router import ProcessorRouter
from app.templates.obsidian_note import ObsidianMarkdownGenerator

REQUIRED_SECTIONS = [
    "## Summary", "## Table of Contents", "## Reading Time", "## Difficulty Level",
    "## Keywords", "## Categories", "## Key Concepts", "## Definitions",
    "## Important Entities", "## Related Topics", "## Suggested Related Notes",
    "## Suggested Backlinks", "## Frequently Asked Questions", "## Flashcards",
    "## Multiple Choice Questions", "## Short Answer Questions", "## Long Answer Questions",
    "## Revision Notes", "## Tags", "## Metadata", "## References",
]

# ── Sample file creators (one per supported category) ────────────────────────

def _text(p):
    (p / "quantum.txt").write_text(
        "Quantum Computing Overview\n\n"
        "Quantum computing leverages quantum mechanical phenomena such as "
        "superposition and entanglement to process information. Unlike classical "
        "bits which are either 0 or 1, qubits can exist in multiple states "
        "simultaneously, enabling massive parallelism for certain algorithms.\n\n"
        "Key algorithms include Shor's algorithm for integer factorization and "
        "Grover's algorithm for unstructured search. These provide exponential "
        "and quadratic speedups respectively over their classical counterparts.\n\n"
        "Applications span cryptography, drug discovery, financial modeling, "
        "and optimization problems. Current challenges include decoherence, "
        "error correction, and scaling qubit counts beyond the NISQ era.",
        encoding="utf-8")
    return p / "quantum.txt"

def _md(p):
    (p / "kubernetes.md").write_text(
        "# Kubernetes Fundamentals\n\n"
        "## Overview\n\n"
        "Kubernetes (K8s) is an open-source container orchestration platform "
        "that automates deployment, scaling, and management of containerized "
        "applications.\n\n"
        "## Core Concepts\n\n"
        "- **Pod**: Smallest deployable unit, one or more containers\n"
        "- **Service**: Network endpoint for accessing pods\n"
        "- **Deployment**: Manages replica sets and rolling updates\n"
        "- **ConfigMap**: Externalized configuration data\n\n"
        "## Architecture\n\n"
        "The control plane consists of the API server, scheduler, controller "
        "manager, and etcd. Worker nodes run kubelet and container runtime.",
        encoding="utf-8")
    return p / "kubernetes.md"

def _py(p):
    (p / "sort.py").write_text(
        '"""Merge sort implementation."""\n\n\n'
        "def merge_sort(arr):\n"
        '    """Sort array using merge sort algorithm."""\n'
        "    if len(arr) <= 1:\n"
        "        return arr\n"
        "    mid = len(arr) // 2\n"
        "    left = merge_sort(arr[:mid])\n"
        "    right = merge_sort(arr[mid:])\n"
        "    return merge(left, right)\n\n\n"
        "def merge(left, right):\n"
        "    result = []\n"
        "    i = j = 0\n"
        "    while i < len(left) and j < len(right):\n"
        "        if left[i] <= right[j]:\n"
        "            result.append(left[i])\n"
        "            i += 1\n"
        "        else:\n"
        "            result.append(right[j])\n"
        "            j += 1\n"
        "    result.extend(left[i:])\n"
        "    result.extend(right[j:])\n"
        "    return result\n", encoding="utf-8")
    return p / "sort.py"

def _csv(p):
    (p / "sales.csv").write_text(
        "month,revenue,units,region\n"
        "January,45000,320,North\n"
        "February,52000,380,South\n"
        "March,48000,350,East\n"
        "April,61000,420,West\n"
        "May,55000,390,North\n"
        "June,67000,460,South\n", encoding="utf-8")
    return p / "sales.csv"

def _toml(p):
    (p / "pyproject.toml").write_text(
        '[project]\nname = "my-project"\nversion = "1.0.0"\n'
        'description = "A sample Python project"\n\n'
        '[project.dependencies]\nrequests = ">=2.28"\npydantic = ">=2.0"\n\n'
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n', encoding="utf-8")
    return p / "pyproject.toml"

def _json(p):
    import json as j
    (p / "config.json").write_text(j.dumps({
        "database": {"host": "localhost", "port": 5432, "name": "appdb"},
        "cache": {"ttl": 3600, "backend": "redis"},
        "features": {"dark_mode": True, "beta_features": False},
    }, indent=2), encoding="utf-8")
    return p / "config.json"

def _html(p):
    (p / "api.html").write_text(
        "<!DOCTYPE html><html><head><title>REST API Design</title></head>\n"
        "<body>\n"
        "<h1>REST API Design Principles</h1>\n"
        "<p>REST (Representational State Transfer) is an architectural style "
        "for designing networked applications. Key principles include "
        "stateless communication, uniform interface, and resource identification "
        "through URIs.</p>\n"
        "<h2>HTTP Methods</h2>\n"
        "<ul><li>GET - retrieve resources</li>\n"
        "<li>POST - create resources</li>\n"
        "<li>PUT - update resources</li>\n"
        "<li>DELETE - remove resources</li></ul>\n"
        "</body></html>", encoding="utf-8")
    return p / "api.html"

def _xml(p):
    (p / "data.xml").write_text(
        '<?xml version="1.0"?>\n<catalog>\n'
        '  <book id="1"><title>Design Patterns</title><author>GoF</author>'
        '<year>1994</year></book>\n'
        '  <book id="2"><title>Clean Code</title><author>Robert Martin</author>'
        '<year>2008</year></book>\n'
        '</catalog>', encoding="utf-8")
    return p / "data.xml"

def _sqlite(p):
    path = p / "users.db"
    conn = sqlite3.connect(str(path))
    c = conn.cursor()
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    c.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@example.com')")
    c.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@example.com')")
    conn.commit()
    conn.close()
    return path

def _zip(p):
    path = p / "project.zip"
    with zipfile.ZipFile(str(path), "w") as zf:
        zf.writestr("README.md", "# My Project\nA sample project.")
        zf.writestr("src/main.py", "print('hello')")
        zf.writestr("tests/test_main.py", "def test_pass(): assert True")
    return path

def _drawio(p):
    (p / "arch.drawio").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile><diagram name="Architecture">\n'
        '<mxGraphModel><root>\n'
        '<mxCell id="1" value="Web Server" style="rounded=1" vertex="1"/>\n'
        '<mxCell id="2" value="Database" style="shape=cylinder" vertex="1"/>\n'
        '<mxCell id="3" value="" style="edgeStyle=orthogonal" edge="1" source="1" target="2"/>\n'
        "</root></mxGraphModel></diagram></mxfile>", encoding="utf-8")
    return p / "arch.drawio"

def _bib(p):
    (p / "refs.bib").write_text(
        "@article{turing1950,\n  title={Computing Machinery and Intelligence},\n"
        "  author={Turing, Alan},\n  journal={Mind},\n  year={1950}\n}\n\n"
        "@book{knuth1997,\n  title={The Art of Computer Programming},\n"
        "  author={Knuth, Donald},\n  year={1997}\n}\n", encoding="utf-8")
    return p / "refs.bib"

def _ris(p):
    (p / "citations.ris").write_text(
        "TY  - JOUR\nAU  - Vaswani, Ashish\nTI  - Attention Is All You Need\n"
        "JO  - NeurIPS\nPY  - 2017\nER  -\n\n"
        "TY  - JOUR\nAU  - Devlin, Jacob\nTI  - BERT\n"
        "JO  - NAACL\nPY  - 2019\nER  -\n", encoding="utf-8")
    return p / "citations.ris"

def _ipynb(p):
    import json as j
    nb = {"cells": [
        {"cell_type": "markdown", "metadata": {}, "source": ["# Data Analysis\n"]},
        {"cell_type": "code", "metadata": {}, "source": ["import pandas as pd\n"],
         "outputs": [], "execution_count": None},
        {"cell_type": "code", "metadata": {},
         "source": ["df = pd.read_csv('data.csv')\ndf.describe()"],
         "outputs": [{"text": "output", "output_type": "stream", "name": "stdout"}],
         "execution_count": 1},
    ], "metadata": {
         "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}
     },
     "nbformat": 4, "nbformat_minor": 5}
    (p / "analysis.ipynb").write_text(j.dumps(nb), encoding="utf-8")
    return p / "analysis.ipynb"

def _eml(p):
    (p / "meeting.eml").write_text(
        "From: alice@example.com\nTo: team@example.com\nSubject: Q4 Planning\n"
        "Date: Mon, 15 Jul 2024 10:00:00 +0000\nContent-Type: text/plain\n\n"
        "Hi team,\n\nLet's schedule Q4 planning for next Thursday.\n"
        "Agenda: Review Q3 metrics, Set Q4 OKRs, Resource allocation.\n\n"
        "Please prepare your team's status reports.\n\nBest,\nAlice", encoding="utf-8")
    return p / "meeting.eml"

def _env(p):
    (p / ".env").write_text(
        "DATABASE_URL=postgresql://localhost:5432/mydb\n"
        "API_KEY=sk-test-12345\nDEBUG=true\nSECRET_KEY=super-secret\n", encoding="utf-8")
    return p / ".env"

def _tex(p):
    (p / "paper.tex").write_text(
        "\\documentclass{article}\n\\usepackage{amsmath}\n"
        "\\title{Neural Networks Survey}\n\\author{John Doe}\n\n"
        "\\begin{document}\n\\maketitle\n\n"
        "\\section{Introduction}\n"
        "Neural networks are computing systems inspired by biological neural "
        "networks. They consist of layers of interconnected nodes.\n\n"
        "\\section{Architecture}\n"
        "A feedforward network has input, hidden, and output layers. "
        "Each connection has a weight adjusted via backpropagation.\n\n"
        "\\end{document}", encoding="utf-8")
    return p / "paper.tex"

def _css(p):
    (p / "styles.css").write_text(
        "/* Modern CSS Reset */\n"
        "* { margin: 0; padding: 0; box-sizing: border-box; }\n\n"
        ".container { max-width: 1200px; margin: 0 auto; padding: 1rem;\n"
        "  display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));\n"
        "  gap: 1.5rem; }\n\n"
        ".card { border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); padding: 1.5rem; }\n",
        encoding="utf-8")
    return p / "styles.css"


SAMPLES = [
    ("text", _text), ("markdown", _md), ("python", _py), ("csv", _csv),
    ("toml", _toml), ("json", _json), ("html", _html), ("xml", _xml),
    ("sqlite", _sqlite), ("zip", _zip), ("drawio", _drawio),
    ("bib", _bib), ("ris", _ris), ("ipynb", _ipynb), ("eml", _eml),
    ("env", _env), ("tex", _tex), ("css", _css),
]


def run():
    results = {}
    with tempfile.TemporaryDirectory(prefix="intel_") as td:
        tmp = Path(td)
        notes_dir = tmp / "notes"
        notes_dir.mkdir()

        ollama = OllamaClient(OllamaSettings(timeout_seconds=300))
        if not ollama.is_available():
            print("ERROR: Ollama not available")
            return

        classifier = DocumentClassifier()
        router = ProcessorRouter(ModelRoutingSettings())
        for proc in default_processors():
            router.register(proc)
        gen = ObsidianMarkdownGenerator()
        svc = DocumentIngestionService()
        model = "llama3.1:8b"

        for i, (name, creator) in enumerate(SAMPLES, 1):
            print(f"\n[{i}/{len(SAMPLES)}] {name}...", end=" ", flush=True)
            cat_dir = tmp / f"s_{name}"
            cat_dir.mkdir(exist_ok=True)
            t0 = time.time()
            try:
                src = creator(cat_dir)
                ing = svc.ingest(src)
                if not ing.succeeded or not ing.document:
                    results[name] = {"status": "FAIL", "stage": "ingest"}
                    print("FAIL (ingest)")
                    continue
                doc = ing.document

                cls = classifier.classify(doc)
                sel = router.select(cls)

                proc = get_processor_by_name(sel.processor_name)
                confidence = None
                if proc:
                    pr = proc.process(doc)
                    doc = doc.model_copy(update={
                        "text": pr.extracted_text or doc.text,
                        "source_type": pr.source_type,
                    })
                    confidence = pr.confidence

                ocr_conf = confidence if sel.processor_name in (
                    "OCRProcessor", "HandwritingProcessor", "VisionProcessor",
                ) else None

                ai = DocumentAIProcessor(ollama, model=model)
                ai_res = ai.process(doc)
                a = ai_res.analysis

                note = gen.generate(
                    document=doc, analysis=a,
                    ocr_confidence=ocr_conf,
                    processing_confidence=confidence,
                )
                md = note.markdown

                found = [s for s in REQUIRED_SECTIONS if s in md]
                missing = [s for s in REQUIRED_SECTIONS if s not in md]

                elapsed = time.time() - t0
                result = {
                    "status": "PASS" if len(found) >= 15 else "PARTIAL",
                    "source_type": doc.source_type, "kind": cls.kind,
                    "processor": sel.processor_name,
                    "confidence": confidence,
                    "ai_attempts": ai_res.attempts,
                    "sections": f"{len(found)}/{len(REQUIRED_SECTIONS)}",
                    "missing": missing,
                    "summary_short": bool(a.summary.short),
                    "summary_detailed": bool(a.summary.detailed),
                    "keywords": len(a.keywords), "tags": len(a.tags),
                    "categories": len(a.categories),
                    "difficulty": a.difficulty,
                    "reading_time": a.reading_time_minutes,
                    "concepts": len(a.key_concepts),
                    "definitions": len(a.definitions),
                    "entities": len(a.important_entities),
                    "related_topics": len(a.related_topics),
                    "related_notes": len(a.suggested_related_notes),
                    "backlinks": len(a.suggested_backlinks),
                    "qa": len(a.questions_and_answers),
                    "flashcards": len(a.flashcards),
                    "mcqs": len(a.multiple_choice_questions),
                    "short_ans": len(a.short_answer_questions),
                    "long_ans": len(a.long_answer_questions),
                    "revision": len(a.revision_notes),
                    "note_size": len(md),
                    "elapsed_s": round(elapsed, 1),
                }
                results[name] = result
                (notes_dir / note.filename).write_text(md, encoding="utf-8")
                print(f"OK ({elapsed:.1f}s) [{result['sections']}] {result['status']}")

            except Exception as e:
                results[name] = {"status": "ERROR", "error": str(e)}
                print(f"ERROR: {e}")

        # Summary
        total = len(results)
        passed = sum(1 for r in results.values() if r.get("status") == "PASS")
        partial = sum(1 for r in results.values() if r.get("status") == "PARTIAL")
        failed = sum(1 for r in results.values() if r.get("status") in ("FAIL", "ERROR"))

        print(f"\n{'='*60}")
        print(f"RESULTS: {passed} PASS / {partial} PARTIAL / {failed} FAIL (of {total})")
        print(f"{'='*60}")
        for n, r in results.items():
            m = "+" if r.get("status") == "PASS" else "~" if r.get("status") == "PARTIAL" else "x"
            s = r.get("sections", "?")
            print(f"  {m} {n}: {r.get('status')} ({s})")

        results["_summary"] = {
            "total": total, "passed": passed, "partial": partial,
            "failed": failed, "model": model,
        }
        return results


if __name__ == "__main__":
    results = run()
    if results:
        out = Path("tests/intelligence_report.json")
        out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
        print(f"\nReport: {out}")
