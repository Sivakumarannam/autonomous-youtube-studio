# Fix missing Any import
from typing import Any


class YouTubeStudioException(Exception):
    """Base exception for all app errors."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(YouTubeStudioException):
    def __init__(self, resource: str, identifier: Any = None):
        msg = f"{resource} not found" + (f": {identifier}" if identifier else "")
        super().__init__(msg, "NOT_FOUND")


class ValidationError(YouTubeStudioException):
    def __init__(self, message: str):
        super().__init__(message, "VALIDATION_ERROR")


class AgentError(YouTubeStudioException):
    def __init__(self, agent: str, message: str):
        super().__init__(f"Agent [{agent}] error: {message}", "AGENT_ERROR")


class LLMProviderError(YouTubeStudioException):
    def __init__(self, provider: str, message: str):
        super().__init__(f"LLM Provider [{provider}] error: {message}", "LLM_ERROR")


class StorageError(YouTubeStudioException):
    def __init__(self, message: str):
        super().__init__(message, "STORAGE_ERROR")


class QualityError(YouTubeStudioException):
    def __init__(self, score: float, threshold: float):
        super().__init__(
            f"Quality score {score} below threshold {threshold}", "QUALITY_ERROR"
        )


class SeoError(YouTubeStudioException):
    """Raised when a script's deterministic SEO gate score falls below threshold.

    Non-retryable: the score is computed from already-stored metadata with no
    network calls, so retrying cannot change the outcome.
    """
    def __init__(self, score: float, threshold: float):
        super().__init__(
            f"SEO gate score {score:.1f} below threshold {threshold}", "SEO_ERROR"
        )
        self.score = score
        self.threshold = threshold


class ModerationError(YouTubeStudioException):
    def __init__(self, reason: str):
        super().__init__(f"Content moderation failed: {reason}", "MODERATION_ERROR")


class UploadError(YouTubeStudioException):
    def __init__(self, message: str):
        super().__init__(message, "UPLOAD_ERROR")


class AuthenticationError(YouTubeStudioException):
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, "AUTH_ERROR")


class AuthorizationError(YouTubeStudioException):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(message, "AUTHZ_ERROR")


class PipelineError(YouTubeStudioException):
    """Raised when the pipeline halts at a named stage."""
    def __init__(self, stage: str, reason: str):
        super().__init__(
            f"Pipeline failed at stage '{stage}': {reason}", "PIPELINE_ERROR"
        )
        self.stage = stage


class PublishError(YouTubeStudioException):
    """Raised for illegal publish-status transitions."""
    def __init__(self, message: str):
        super().__init__(message, "PUBLISH_ERROR")