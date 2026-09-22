"""Immutable identifiers for analysis implementations and result schemas."""

DETERMINISTIC_PROMPT_VERSION = "deterministic-v2"
SEMANTIC_PROMPT_VERSION = "semantic-v3"
ANALYSIS_SCHEMA_VERSION = "2"


def prompt_version_for_job(job_type: str) -> str:
    """Return the implementation version persisted for an analysis job."""

    if job_type == "run_deterministic_analysis":
        return DETERMINISTIC_PROMPT_VERSION
    if job_type == "run_semantic_analysis":
        return SEMANTIC_PROMPT_VERSION
    raise ValueError(f"Unsupported analysis job type: {job_type}")
