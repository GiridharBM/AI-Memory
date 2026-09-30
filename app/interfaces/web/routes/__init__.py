"""GUI transport routes.

Each module re-exposes an operation that already exists in the PAM CLI or
application layer over HTTP, and returns JSON instead of a Rich table. No
retrieval, QA, storage or configuration logic lives here.
"""
