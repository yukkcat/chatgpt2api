from __future__ import annotations

from services.image_failure import ImageFailure, image_failure


EDITABLE_FILE_AUTH_PUBLIC_MESSAGE = (
    "The editable file task could not authenticate with the upstream account. "
    "Please try another account."
)
EDITABLE_FILE_REQUEST_PUBLIC_MESSAGE = (
    "The editable file request was rejected by the upstream service."
)
EDITABLE_FILE_UNAVAILABLE_PUBLIC_MESSAGE = (
    "The editable file service is temporarily unavailable. Please try again later."
)
EDITABLE_FILE_DOWNLOAD_PUBLIC_MESSAGE = (
    "The editable file output could not be downloaded. Please try again."
)
EDITABLE_FILE_TRANSFER_PUBLIC_MESSAGE = (
    "An editable file asset could not be transferred. Please try again."
)
EDITABLE_FILE_TIMEOUT_PUBLIC_MESSAGE = (
    "The editable file task timed out. Please try again."
)
EDITABLE_FILE_ERROR_PUBLIC_MESSAGE = (
    "The editable file task failed. Please try again."
)


def public_editable_file_error_message(failure: ImageFailure) -> str:
    """Project a shared upstream failure into the Editable File domain."""
    if failure.code == "auth_invalid":
        return EDITABLE_FILE_AUTH_PUBLIC_MESSAGE
    if failure.code in {
        "content_policy_violation",
        "invalid_image_input",
        "upstream_text_reply",
        "unsupported_model",
    }:
        return EDITABLE_FILE_REQUEST_PUBLIC_MESSAGE
    if failure.code in {
        "file_upload_throttled",
        "image_quota_exhausted",
        "insufficient_quota",
        "upstream_rate_limited",
        "upstream_unavailable",
    }:
        return EDITABLE_FILE_UNAVAILABLE_PUBLIC_MESSAGE
    if failure.code == "image_download_failed":
        return EDITABLE_FILE_DOWNLOAD_PUBLIC_MESSAGE
    if failure.scope == "delivery":
        return EDITABLE_FILE_TRANSFER_PUBLIC_MESSAGE
    if failure.code in {
        "image_poll_timeout",
        "image_stream_timeout",
        "upstream_connection_timeout",
    }:
        return EDITABLE_FILE_TIMEOUT_PUBLIC_MESSAGE
    return EDITABLE_FILE_ERROR_PUBLIC_MESSAGE


class EditableFileFailureError(RuntimeError):
    """Structured Editable File failure with a domain-specific public message."""

    def __init__(self, *, failure: ImageFailure | None = None) -> None:
        self.failure = failure or image_failure("upstream_error")
        self.status_code = self.failure.status_code
        self.error_type = self.failure.error_type
        super().__init__(public_editable_file_error_message(self.failure))
