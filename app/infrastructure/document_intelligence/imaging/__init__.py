"""Image preprocessing package — shared module for OCR (P2-104) and Milestone 2.5."""

from app.infrastructure.document_intelligence.imaging.preprocess import (
    Preprocessor,
    preprocess_image,
)

__all__ = ["Preprocessor", "preprocess_image"]
