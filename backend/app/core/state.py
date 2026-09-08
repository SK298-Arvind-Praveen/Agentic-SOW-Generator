"""
State definition for ShellKodeSOW LangGraph Agent
"""
from typing import TypedDict, Dict, Any, List, Optional

class AgentState(TypedDict):
    """
    Represents the state of the POC generation agent.
    """
    metadata: Dict[str, Any]
    objective: str
    additional_details: Optional[str]  # User guidance; uploaded evidence takes precedence
    analyzed_requirements: Optional[Dict[str, Any]]
    validated_requirements: Optional[Dict[str, Any]]
    poc_content: Optional[Dict[str, Any]]
    output_path: Optional[str]
    json_path: Optional[str]
    errors: Optional[List[str]]
    current_step: str
    mode: str  # 'POC', 'PROD', 'POC_TO_PROD'
    source_file: Optional[str]  # For POC_TO_PROD mode
    rag_context: Optional[Dict[str, Any]]  # RAG data context
    is_poc_table_conversion: Optional[bool]  # Flag for POC table conversion
    supporting_documents: Optional[List[str]]  # Paths to supporting documents
    supporting_context: Optional[str]  # Extracted content from supporting documents
    selected_sow_sections: Optional[List[str]]  # User-selected optional section IDs
    progress_callback: Optional[Any]  # In-process preview progress reporter
    pricing_result: Optional[Dict[str, Any]]  # Validated AWS Calculator result and provenance
    scope_architecture_plan: Optional[Dict[str, Any]]  # Dedicated architect-approved deliverable/module plan
    scope_architecture_issues: Optional[List[str]]  # Visible classification failure/audit details
    scope_generation_seconds: Optional[float]  # Scope architecture elapsed time for final run timing
    preview_started_at: Optional[float]  # Monotonic request start used for total preview timing
    token_usage: Optional[Dict[str, Any]]  # Per-SOW Bedrock usage audit
    total_tokens: Optional[int]  # Input plus output tokens consumed by this SOW
    refinement_request: Optional[Dict[str, Any]]  # Baseline SOW, user instructions, and source-document delta
    refinement_plan: Optional[Dict[str, Any]]  # Standalone refinement agent's concise change plan
