"""
Graph definition for the LangGraph agent workflow
"""
import sys
from pathlib import Path
_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from langgraph.graph import StateGraph, END
from app.core.state import AgentState
from app.core.nodes import (
    poc_ingestion_node,
    research_node,
    analyze_objective_node,
    rule_validation_node,
    scope_architecture_node,
    aws_pricing_node,
    content_generation_node,
    pdf_build_node
)

def create_graph():
    """
    Create and compile the LangGraph workflow
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("ingest", poc_ingestion_node)
    workflow.add_node("research", research_node)
    workflow.add_node("analyze", analyze_objective_node)
    workflow.add_node("validate", rule_validation_node)
    workflow.add_node("scope_architecture", scope_architecture_node)
    workflow.add_node("pricing", aws_pricing_node)
    workflow.add_node("generate", content_generation_node)
    workflow.add_node("build", pdf_build_node)
    
    # Define conditional entry point
    def select_entry_point(state):
        if state.get("mode") == "POC_TO_PROD":
            return "ingest"
        return "research"
    
    workflow.set_conditional_entry_point(
        select_entry_point,
        {
            "ingest": "ingest",
            "research": "research"
        }
    )
    
    # Define edges
    def check_ingestion_status(state):
        if state.get("errors"):
            return END
        return "research"

    workflow.add_conditional_edges(
        "ingest",
        check_ingestion_status,
        {
            END: END,
            "research": "research"
        }
    )
    # workflow.add_edge("ingest", "research") # Removed unconditional edge
    workflow.add_edge("research", "analyze")
    workflow.add_conditional_edges(
        "analyze", lambda state: END if state.get("errors") else "validate",
        {END: END, "validate": "validate"},
    )
    workflow.add_edge("validate", "scope_architecture")
    workflow.add_edge("scope_architecture", "pricing")
    workflow.add_edge("pricing", "generate")
    workflow.add_edge("generate", "build")
    workflow.add_edge("build", END)
    
    # Compile
    app = workflow.compile()
    return app


def create_preview_graph():
    """
    Create and compile the LangGraph workflow for PREVIEW ONLY
    Stops after content generation (before document building)
    """
    workflow = StateGraph(AgentState)
    
    # Add nodes (excluding build node)
    workflow.add_node("ingest", poc_ingestion_node)
    workflow.add_node("research", research_node)
    workflow.add_node("analyze", analyze_objective_node)
    workflow.add_node("validate", rule_validation_node)
    workflow.add_node("scope_architecture", scope_architecture_node)
    workflow.add_node("pricing", aws_pricing_node)
    workflow.add_node("generate", content_generation_node)
    
    # Define conditional entry point
    def select_entry_point(state):
        if state.get("mode") == "POC_TO_PROD":
            return "ingest"
        return "research"
    
    workflow.set_conditional_entry_point(
        select_entry_point,
        {
            "ingest": "ingest",
            "research": "research"
        }
    )
    
    # Define edges (stop after generate)
    def check_ingestion_status(state):
        if state.get("errors"):
            return END
        return "research"

    workflow.add_conditional_edges(
        "ingest",
        check_ingestion_status,
        {
            END: END,
            "research": "research"
        }
    )
    workflow.add_edge("research", "analyze")
    workflow.add_conditional_edges(
        "analyze", lambda state: END if state.get("errors") else "validate",
        {END: END, "validate": "validate"},
    )
    workflow.add_edge("validate", "scope_architecture")
    workflow.add_edge("scope_architecture", "pricing")
    workflow.add_edge("pricing", "generate")
    workflow.add_edge("generate", END)  # Stop here, don't build document
    
    # Compile
    app = workflow.compile()
    return app


def create_fast_preview_graph():
    """
    Create optimized preview graph with performance improvements:
    - Same nodes but with fast_mode flag
    - Reduced processing where possible
    """
    workflow = StateGraph(AgentState)
    
    # Add same nodes but they'll check for fast_mode in state
    workflow.add_node("ingest", poc_ingestion_node)
    workflow.add_node("research", research_node)
    workflow.add_node("analyze", analyze_objective_node)
    workflow.add_node("validate", rule_validation_node)
    workflow.add_node("scope_architecture", scope_architecture_node)
    workflow.add_node("pricing", aws_pricing_node)
    workflow.add_node("generate", content_generation_node)
    
    # Define conditional entry point
    def select_entry_point(state):
        if state.get("mode") == "POC_TO_PROD":
            return "ingest"
        return "research"
    
    workflow.set_conditional_entry_point(
        select_entry_point,
        {
            "ingest": "ingest",
            "research": "research"
        }
    )
    
    # Define edges
    def check_ingestion_status(state):
        if state.get("errors"):
            return END
        return "research"

    workflow.add_conditional_edges(
        "ingest",
        check_ingestion_status,
        {
            END: END,
            "research": "research"
        }
    )
    workflow.add_edge("research", "analyze")
    workflow.add_conditional_edges(
        "analyze", lambda state: END if state.get("errors") else "validate",
        {END: END, "validate": "validate"},
    )
    workflow.add_edge("validate", "scope_architecture")
    workflow.add_edge("scope_architecture", "pricing")
    workflow.add_edge("pricing", "generate")
    workflow.add_edge("generate", END)
    
    # Compile
    app = workflow.compile()
    return app
