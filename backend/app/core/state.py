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
