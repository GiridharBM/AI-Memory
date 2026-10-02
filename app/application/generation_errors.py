"""Small typed failure hierarchy for V2 generation.

Every failure the executor can report, mirroring the project's simple
exception conventions (cf. ``InvalidJobTransitionError``): flat
``ValueError`` subclasses, no deep hierarchy.
"""


class GenerationError(ValueError):
    """Base class for V2 generation failures."""


class UnsupportedTaskError(GenerationError):
    """No task handler is registered for the requested task type."""


class UnsupportedScopeError(GenerationError):
    """The request's memory scope cannot be resolved or retrieved."""


class RetrievalError(GenerationError):
    """Memory retrieval for the request failed."""


class HandlerError(GenerationError):
    """The task handler itself failed."""


class GenerationValidationError(GenerationError):
    """A generation result failed structural validation."""


class ArtifactPersistError(GenerationError):
    """The generated artifact could not be persisted."""


class ProvenancePersistError(GenerationError):
    """Provenance records could not be persisted."""


class JobCancelled(GenerationError):
    """Control-flow signal: cancellation was observed, not a defect."""
