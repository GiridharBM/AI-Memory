"""Local HTTP interface for PAM (V1 GUI).

Read-mostly adapter over the existing application and infrastructure layers.
This package adds a transport and nothing else: it never reimplements or
tunes retrieval, chunking, embedding, BM25, RRF, QA generation, abstention or
configuration, and it never writes durable state outside what the existing
ingestion workflow already writes.

Install with the optional extra::

    pip install -e ".[gui]"
    pam-gui            # or: uvicorn app.interfaces.web.server:app
"""
