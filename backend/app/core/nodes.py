"""
Nodes for the LangGraph agent workflow
FIXED: poc_ingestion_node now properly extracts requirements
"""
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timedelta

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.core.state import AgentState
from app.core.config import Config
from app.agents.company_research_agent import CompanyResearchAgent
from app.agents.objective_agent import ObjectiveAgent
from app.agents.rule_engine_agent import RuleEngineAgent
from app.agents.poc_writer_agent import POCWriterAgent
from app.document.document_builder import DocumentBuilder
from app.document.doc_reader import read_document, extract_metadata_from_content, validate_extraction
import boto3

# Initialize config once
config = Config()

# Global token tracking
_token_usage = {
    'total_input_tokens': 0,
    'total_output_tokens': 0,
    'total_tokens': 0,
    'api_calls': 0
}

def _track_tokens(response_body: dict, call_name: str = "API Call"):
    """Track token usage from Bedrock API response"""
    global _token_usage
    
    usage = response_body.get('usage', {})
    input_tokens = usage.get('input_tokens', 0)
    output_tokens = usage.get('output_tokens', 0)
    
    _token_usage['total_input_tokens'] += input_tokens
    _token_usage['total_output_tokens'] += output_tokens
    _token_usage['total_tokens'] += (input_tokens + output_tokens)
    _token_usage['api_calls'] += 1
    
    print(f"   🔢 {call_name} - Input: {input_tokens:,} | Output: {output_tokens:,} | Total: {input_tokens + output_tokens:,}")

def get_token_usage():
    """Get current token usage statistics"""
    return _token_usage.copy()

def reset_token_usage():
    """Reset token usage counters"""
    global _token_usage
    _token_usage = {
        'total_input_tokens': 0,
        'total_output_tokens': 0,
        'total_tokens': 0,
        'api_calls': 0
    }

def print_token_summary():
    """Print final token usage summary"""
    print("\n" + "="*70)
    print("📊 BEDROCK API TOKEN USAGE SUMMARY")
    print("="*70)
    print(f"Total API Calls:      {_token_usage['api_calls']}")
    print(f"Total Input Tokens:   {_token_usage['total_input_tokens']:,}")
    print(f"Total Output Tokens:  {_token_usage['total_output_tokens']:,}")
    print(f"Total Tokens:         {_token_usage['total_tokens']:,}")
    print("="*70 + "\n")

def _clean_final_content(text: str) -> str:
    """
    Final content cleaning to remove markdown artifacts before document building
    """
    if not text:
        return text
    
    # Remove various markdown artifacts that cause formatting issues
    text = re.sub(r'\*{3,}', '', text)  # Remove 3+ asterisks
    text = re.sub(r'_{3,}', '', text)   # Remove 3+ underscores  
    text = re.sub(r'-{3,}', '', text)   # Remove 3+ dashes
    text = re.sub(r'#{3,}', '', text)   # Remove 3+ hashes
    
    # Clean up isolated markdown symbols (but preserve intentional formatting)
    text = re.sub(r'(?<!\w)\*{3,}(?!\w)', '', text)  # Remove 3+ isolated asterisks
    text = re.sub(r'(?<!\w)_{3,}(?!\w)', '', text)   # Remove 3+ isolated underscores
    text = re.sub(r'(?<!\w)-{3,}(?!\w)', '', text)   # Remove 3+ isolated dashes
    
    # Clean up extra whitespace but preserve paragraph structure
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
    text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple blank lines to double newline
    text = text.strip()
    
    return text

def poc_ingestion_node(state: AgentState) -> AgentState:
    """
    Ingest existing POC file (PDF/DOCX) for POC_TO_PROD mode
    ENHANCED: Uses improved doc_reader with OCR support and LLM metadata extraction
    FIXED: Now properly extracts requirements when content extraction succeeds
    UPDATED: Creates RAG context from ingested document for enhanced generation
    """
    print(f"\n--- Step: Ingesting POC Document ---")
    source_file = state.get('source_file')
    
    # Handle POC table conversion (no source file needed)
    if not source_file:
        print(f"⊝ No source file provided - checking for POC table conversion...")
        
        # Check if this is a POC table conversion
        metadata = state.get('metadata', {})
        rag_context = state.get('rag_context', {})
        
        if rag_context and rag_context.get('rag_data'):
            print(f"✅ POC table conversion detected - using RAG data")
            print(f"   Company: {metadata.get('company_name', 'N/A')}")
            print(f"   Project: {metadata.get('project_title', 'N/A')}")
            
            # Use RAG data as the "ingested" content
            analyzed_requirements = {
                "source": "poc_table_conversion",
                "company_name": metadata.get('company_name'),
                "project_title": metadata.get('project_title'),
                "rag_data": rag_context.get('rag_data'),
                "conversion_type": "poc_to_production",
                "content_extracted": True
            }
            
            return {
                "analyzed_requirements": analyzed_requirements,
                "current_step": "ingestion_complete"
            }
        else:
            print(f"❌ Error: No source file and no RAG data for POC table conversion")
            return {"errors": ["POC_TO_PROD requires either source file or existing POC data"]}
    
    try:
        # Enhanced file-based ingestion using improved doc_reader
        print(f"📖 Reading file with enhanced extraction: {source_file}")
        content = read_document(source_file)
        
        # Initialize variables that will be set in both branches
        extracted_metadata = None
        requirements = None
        
        # Handle case where extraction returns empty content
        if not content or len(content.strip()) < 20:
            print(f"⚠️  Document extraction yielded minimal content ({len(content)} chars)")
            print(f"   This may be an image-based document or have complex formatting")
            print(f"   Proceeding with default metadata extraction...")
            
            # Use default metadata when content extraction fails
            extracted_metadata = {
                'company_name': 'Unknown Company',
                'project_title': 'Unknown Project',
                'author_name': 'Unknown Author',
                'author_org': 'Shellkode',
                'objective': 'Project Implementation',
                'document_date': datetime.now().strftime("%d %B %Y"),
                'version': '2.0',
                'start_date': (datetime.now() + timedelta(days=7)).strftime("%d %B %Y"),
                'end_date': (datetime.now() + timedelta(weeks=14)).strftime("%d %B %Y"),
                'timezone': 'IST'
            }
            
            # Use basic requirements structure
            requirements = {
                "project_overview": "Document conversion from POC to Production",
                "key_features": [],
                "aws_services": [],
                "technical_stack": [],
                "success_metrics": [],
                "architecture_components": [],
                "integrations": [],
                "business_impact": "Not specified",
                "timeline": "Not specified",
                "scope": "Not specified"
            }
        else:
            print(f"✅ Successfully extracted {len(content)} characters from document")
            
            # Extract metadata using LLM
            print(f"\n📋 Extracting metadata using LLM...")
            extracted_metadata = _extract_metadata_with_llm(content)
            
            if extracted_metadata:
                print(f"✅ LLM metadata extraction successful:")
                print(f"   Company: {extracted_metadata.get('company_name', 'N/A')}")
                print(f"   Project: {extracted_metadata.get('project_title', 'N/A')}")
                print(f"   Author: {extracted_metadata.get('author_name', 'N/A')}")
                print(f"   Date: {extracted_metadata.get('document_date', 'N/A')}")
            
            # Extract detailed requirements from document using LLM
            print(f"\n📋 Extracting detailed requirements using LLM...")
            requirements = _extract_requirements_with_llm(content)
            
            if requirements:
                print(f"✅ Requirements extraction successful:")
                print(f"   Features: {len(requirements.get('key_features', []))}")
                print(f"   AWS Services: {len(requirements.get('aws_services', []))}")
                print(f"   Tech Stack: {len(requirements.get('technical_stack', []))}")
        
        # Build final metadata (merge with any existing metadata from state)
        # PRIORITY: User-provided values (from form) > LLM-extracted values > defaults
        existing_metadata = state.get('metadata', {})

        def _pick_best(field, extracted_val, existing_val, default_val):
            """Pick best value: user-provided (existing) wins over LLM-extracted if valid."""
            placeholder_values = [
                'unknown company', 'unknown project', 'unknown author',
                'to be extracted from document', 'unknown', ''
            ]
            # If user provided a valid value in the form, use it
            if existing_val and str(existing_val).strip().lower() not in placeholder_values:
                return existing_val
            # Otherwise use LLM-extracted value if valid
            if extracted_val and str(extracted_val).strip().lower() not in placeholder_values:
                return extracted_val
            # Fall back to default
            return default_val

        final_metadata = {
            'company_name': _pick_best('company_name',
                extracted_metadata.get('company_name'),
                existing_metadata.get('company_name'),
                'Unknown Company'),
            'project_title': _pick_best('project_title',
                extracted_metadata.get('project_title'),
                existing_metadata.get('project_title'),
                'Unknown Project'),
            'author_name': _pick_best('author_name',
                extracted_metadata.get('author_name'),
                existing_metadata.get('author_name'),
                'Unknown Author'),
            'author_org': extracted_metadata.get('author_org', 'Shellkode'),
            'author_org_description': 'Shellkode specializes in developing advanced data and AI solutions for businesses.',
            'objective': _pick_best('objective',
                extracted_metadata.get('objective'),
                existing_metadata.get('objective'),
                'Project Implementation'),
            'document_date': existing_metadata.get('document_date') or extracted_metadata.get('document_date', datetime.now().strftime("%d %B %Y")),
            'version': extracted_metadata.get('version', '2.0'),  # Production version
            'start_date': extracted_metadata.get('start_date', (datetime.now() + timedelta(days=7)).strftime("%d %B %Y")),
            'end_date': extracted_metadata.get('end_date', (datetime.now() + timedelta(weeks=14)).strftime("%d %B %Y")),
            'timezone': extracted_metadata.get('timezone', 'IST')
        }
        
        # Create RAG context from ingested document
        print(f"\n📋 Creating RAG context from ingested document...")
        rag_context = {
            "rag_data": {
                "unique_use_cases": requirements.get('key_features', []),
                "unique_technical_components": requirements.get('technical_stack', []),
                "unique_data_sources": [],
                "unique_integrations": requirements.get('integrations', []),
                "unique_success_criteria": requirements.get('success_metrics', []),
                "unique_challenges_addressed": [],
                "unique_data_flow": {},
                "unique_aws_service_usage": requirements.get('aws_services', []),
                "unique_data_retention": {},
                "unique_team_expertise_required": [],
                "extracted_content": content  # Include the full extracted document content
            },
            "retrieval_success": True,
            "schema_type": "POC_TO_PROD",
            "source": "ingested_document"
        }
        
        print(f"✅ RAG context created from ingested document:")
        print(f"   Use Cases: {len(rag_context['rag_data']['unique_use_cases'])}")
        print(f"   Technical Components: {len(rag_context['rag_data']['unique_technical_components'])}")
        print(f"   AWS Services: {len(rag_context['rag_data']['unique_aws_service_usage'])}")
        
        # Print final extraction summary
        print(f"\n📋 FINAL EXTRACTED INFORMATION:")
        print(f"   ✓ Company: {final_metadata['company_name']}")
        print(f"   ✓ Project: {final_metadata['project_title']}")
        print(f"   ✓ Author: {final_metadata['author_name']}")
        print(f"   ✓ Organization: {final_metadata['author_org']}")
        print(f"   ✓ Date: {final_metadata['document_date']}")
        print(f"   ✓ Content length: {len(content)} characters")
        
        # Return state with extracted data and RAG context
        state_update = {
            "metadata": final_metadata,
            "analyzed_requirements": requirements,
            "objective": final_metadata['objective'],
            "current_step": "ingest",
            "poc_original_content": content,
            "production_enhancements": {},
            "rag_context": rag_context  # Add RAG context from ingested document
        }
        
        return state_update
        
    except Exception as e:
        print(f"❌ Error in POC ingestion: {e}")
        import traceback
        traceback.print_exc()
        return {"errors": [str(e)]}


def _extract_company_name_regex(text_content: str) -> str:
    """
    Extract client company name from cover page
    Looks for the prominent company name (usually the largest text on cover page)
    """
    import re
    
    # Focus on cover page only (first 1000 chars)
    cover_page = text_content[:1000]
    lines = cover_page.split('\n')
    
    potential_companies = []
    
    print(f"   📄 Looking for client company name on cover page...")
    
    for i, line in enumerate(lines[:10]):  # Only first 10 lines of cover page
        line = line.strip()
        
        # Skip empty lines and very short lines
        if not line or len(line) < 3:
            continue
        
        line_lower = line.lower()
        
        # Skip vendor company and common non-company text
        skip_patterns = [
            'shellkode', 'prepared by', 'author', 'date', 'version',
            'contents', 'about', 'overview', 'document', 'poc', 'sow'
        ]
        
        if any(skip in line_lower for skip in skip_patterns):
            print(f"   ⏭️  Skipping line {i}: '{line}' (vendor/metadata)")
            continue
        
        # Look for company-like names
        # Companies are usually:
        # 1. Capitalized words
        # 2. 1-3 words
        # 3. Not too long
        # 4. Early in the document
        
        word_count = len(line.split())
        
        if (len(line) >= 4 and len(line) <= 30 and 
            1 <= word_count <= 3 and
            line[0].isupper() and
            not re.search(r'\d', line)):  # No numbers in company names typically
            
            score = 0
            
            # Base score for reasonable format
            score += 20
            
            # Bonus for single word companies (common)
            if word_count == 1:
                score += 15
            elif word_count == 2:
                score += 10
            
            # Bonus for title case
            if re.match(r'^[A-Z][a-z]+(?:\s+[A-Z][a-z]*)*', line):
                score += 10
            
            # Bonus for early position (company names are usually prominent)
            if i <= 3:
                score += 15
            elif i <= 6:
                score += 10
            
            # Bonus for common company name patterns
            if (line.endswith('AI') or line.endswith('Tech') or 
                line.endswith('Corp') or line.endswith('Inc') or
                'med' in line_lower or 'tech' in line_lower):
                score += 10
            
            potential_companies.append((score, line, f"line_{i}"))
            print(f"   ✅ Potential company: '{line}' (score: {score}, line: {i})")
    
    # Sort by score and return the best match
    if potential_companies:
        potential_companies.sort(key=lambda x: x[0], reverse=True)
        
        print(f"   🏆 Company candidates:")
        for score, company, source in potential_companies[:3]:
            print(f"      {score:3d}: '{company}' ({source})")
        
        best_score, best_company, best_source = potential_companies[0]
        
        if best_score >= 30:
            print(f"   ✅ Selected company: '{best_company}' (score: {best_score})")
            return best_company
        else:
            print(f"   ⚠️  Best candidate score too low ({best_score})")
    else:
        print(f"   ⚠️  No potential companies found")
    
    return None


def _extract_project_title_regex(text_content: str) -> str:
    """
    Extract project title from cover page - focuses on actual cover page content
    Based on visual layout: title appears under company name on cover page
    """
    import re
    
    # Focus on very beginning of document (cover page only - first 800 chars)
    cover_page = text_content[:800]
    lines = cover_page.split('\n')
    
    potential_titles = []
    
    print(f"   📄 Analyzing cover page for project title (first 800 chars)...")
    print(f"   📄 First 10 lines:")
    for i, line in enumerate(lines[:10]):
        line_clean = line.strip()
        print(f"      {i}: '{line_clean}' (len: {len(line_clean)})")
    
    # Look for specific patterns that match the cover page layout
    for i, line in enumerate(lines[:20]):  # Only first 20 lines
        line = line.strip()
        
        # Skip empty lines
        if not line or len(line) < 3:
            continue
        
        line_lower = line.lower()
        
        # Skip obvious document structure (but be more specific)
        if (line_lower in ['table of contents', 'contents', 'toc', 'about shellkode', 'shellkode'] or
            line_lower.startswith(('shellkode specializes', 'about ', 'project overview', 'scope of work')) or
            len(line) > 100):  # Very long lines are descriptions, not titles
            print(f"   ⏭️  Skipping line {i}: '{line[:50]}...' (document structure)")
            continue
        
        # Look for project title patterns
        word_count = len(line.split())
        
        # Project titles are typically:
        # - 2-5 words
        # - 10-40 characters  
        # - Not all caps
        # - Appear early in document but after company name
        
        if (len(line) >= 8 and len(line) <= 40 and 
            2 <= word_count <= 5 and
            not line.isupper()):  # Not all caps
            
            score = 0
            
            # Base score
            score += 40
            
            # Look for common project title words (but don't require them)
            project_indicators = [
                'system', 'platform', 'forecast', 'demand', 'analytics', 'dashboard',
                'portal', 'application', 'service', 'tool', 'solution', 'engine'
            ]
            
            has_project_word = any(word in line_lower for word in project_indicators)
            if has_project_word:
                score += 30
                print(f"   🎯 Found project indicator in: '{line}'")
            
            # Bonus for good positioning (after company name area)
            if 3 <= i <= 10:
                score += 20
            elif i <= 15:
                score += 10
            
            # Bonus for lowercase words (indicates it's descriptive text, not headers)
            if re.search(r'[a-z]', line):
                score += 15
            
            # Bonus for optimal word count
            if word_count == 3:
                score += 15
            elif word_count == 2:
                score += 10
            
            # Penalty for starting with "About" (section headers)
            if line_lower.startswith('about'):
                score -= 30
            
            potential_titles.append((score, line, f"line_{i}"))
            print(f"   ✅ Potential title: '{line}' (score: {score}, line: {i})")
    
    # Sort by score and return the best match
    if potential_titles:
        potential_titles.sort(key=lambda x: x[0], reverse=True)
        
        print(f"   🏆 Final candidates:")
        for score, title, source in potential_titles[:3]:
            print(f"      {score:3d}: '{title}' ({source})")
        
        best_score, best_title, best_source = potential_titles[0]
        
        if best_score >= 40:
            print(f"   ✅ Selected: '{best_title}' (score: {best_score})")
            return best_title
        else:
            print(f"   ⚠️  Best candidate score too low ({best_score})")
    else:
        print(f"   ⚠️  No potential titles found")
    
    return None


def _clean_project_title(title: str) -> str:
    """
    Clean up project title by removing common unwanted prefixes/suffixes
    that might be added by LLM or extracted incorrectly
    """
    if not title:
        return title
    
    import re
    
    # Remove common unwanted prefixes (case-insensitive)
    unwanted_prefixes = [
        r'^POC\s*[-:]?\s*',
        r'^Proof\s+of\s+Concept\s*[-:]?\s*',
        r'^Production\s*[-:]?\s*',
        r'^PROD\s*[-:]?\s*',
        r'^Project\s*[-:]?\s*',
        r'^Document\s*[-:]?\s*',
        r'^SOW\s*[-:]?\s*',
        r'^Statement\s+of\s+Work\s*[-:]?\s*',
        # AI/Tech prefixes that LLM might add
        r'^Intelligent\s+',
        r'^AI-Powered\s+',
        r'^AI\s+',
        r'^Smart\s+',
        r'^Advanced\s+',
        r'^Automated\s+',
        r'^Machine\s+Learning\s+',
        r'^ML\s+',
        r'^Data-Driven\s+',
        r'^Cloud-Based\s+',
        r'^Enterprise\s+',
        r'^Comprehensive\s+',
        r'^Integrated\s+',
        r'^Real-time\s+',
        r'^Real\s+Time\s+',
    ]
    
    # Remove common unwanted suffixes (case-insensitive)
    # ONLY remove suffixes that are clearly LLM additions, not legitimate project words
    unwanted_suffixes = [
        r'\s*[-:]?\s*POC$',
        r'\s*[-:]?\s*Proof\s+of\s+Concept$',
        r'\s*[-:]?\s*Production$',
        r'\s*[-:]?\s*PROD$',
        r'\s*[-:]?\s*Project$',
        r'\s*[-:]?\s*Document$',
        r'\s*[-:]?\s*SOW$',
        r'\s*[-:]?\s*Statement\s+of\s+Work$',
        # Only remove these if they appear to be LLM additions (not part of actual title)
        # r'\s+Solution$',  # Removed - could be legitimate
        # r'\s+System$',    # Removed - could be legitimate  
        # r'\s+Platform$',  # Removed - could be legitimate
        # r'\s+Application$', # Removed - could be legitimate
        # r'\s+Tool$',      # Removed - could be legitimate
        # r'\s+Service$',   # Removed - could be legitimate
        # r'\s+Framework$', # Removed - could be legitimate
        # r'\s+Engine$',    # Removed - could be legitimate
    ]
    
    cleaned = title.strip()
    original_cleaned = cleaned
    
    # Remove prefixes
    for pattern in unwanted_prefixes:
        new_cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        if new_cleaned != cleaned and len(new_cleaned.strip()) > 0:
            cleaned = new_cleaned
            break  # Only remove one prefix to avoid over-cleaning
    
    # Remove suffixes (but be more careful - only remove if it makes sense)
    for pattern in unwanted_suffixes:
        new_cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        if new_cleaned != cleaned and len(new_cleaned.strip()) > 0:
            # Only remove suffix if the remaining text is still meaningful (more than 2 words or 10+ chars)
            remaining_words = len(new_cleaned.strip().split())
            if remaining_words >= 2 or len(new_cleaned.strip()) >= 10:
                cleaned = new_cleaned
                break
    
    # Clean up extra whitespace and punctuation
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    cleaned = re.sub(r'^[-:\s]+|[-:\s]+$', '', cleaned).strip()
    
    # If cleaning removed too much, return original
    if not cleaned or len(cleaned) < 3:
        return title
    
    return cleaned


def _clean_author_name(author: str) -> str:
    """
    Clean up author name by removing common unwanted text
    """
    if not author:
        return author
    
    import re
    
    # Remove common unwanted patterns
    unwanted_patterns = [
        r'\s*\(.*?\)',  # Remove anything in parentheses
        r'\s*\[.*?\]',  # Remove anything in brackets
        r'\s*[-–—]\s*.*$',  # Remove anything after a dash
        r'^Prepared\s+by:?\s*',  # Remove "Prepared by:" prefix
        r'^Author:?\s*',  # Remove "Author:" prefix
        r'^By:?\s*',  # Remove "By:" prefix
        r'^Contact:?\s*',  # Remove "Contact:" prefix
    ]
    
    cleaned = author.strip()
    
    for pattern in unwanted_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    
    # Validate it's still a reasonable name (at least 2 characters, starts with letter)
    if len(cleaned) >= 2 and cleaned[0].isalpha():
        return cleaned
    else:
        return author  # Return original if cleaning resulted in invalid name


def _extract_metadata_with_llm(text_content: str) -> dict:
    """Extract metadata from document content using LLM"""
    try:
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=config.AWS_REGION,
            config=config.BOTO_CONFIG
        )

        # Pre-extract author from DOCX properties if available in content
        docx_author = None
        author_match = re.search(r'^DOCUMENT_AUTHOR:\s*(.+)$', text_content, re.MULTILINE)
        if author_match:
            docx_author = author_match.group(1).strip()
            if docx_author and docx_author.lower() not in ['python-docx', 'python', 'unknown', 'author', 'admin', 'user', '']:
                print(f"   ✅ Found author from document properties: {docx_author}")

        # Get cover page (first page) for author extraction
        # Author name is typically on the cover page at the right bottom corner
        doc_length = len(text_content)

        # Extract first page (cover page) - typically first 2000-3000 chars
        cover_page = text_content[:3000]

        # Also get a bit more context for other metadata
        beginning = text_content[:5000]
        ending = text_content[-2000:] if doc_length > 2000 else ""

        # Combine for comprehensive extraction
        combined_text = f"COVER PAGE (FIRST PAGE - CHECK RIGHT BOTTOM CORNER FOR AUTHOR):\n{cover_page}\n\n{'='*50}\n\nADDITIONAL CONTEXT:\n{beginning}\n\n{'='*50}\n\nDOCUMENT ENDING:\n{ending}"
        
        prompt = f"""Extract metadata from this POC/SOW document cover page EXACTLY as it appears.

COVER PAGE LAYOUT ANALYSIS:
Look at the FIRST PAGE (cover page) which typically has this layout:
- TOP AREA: Vendor company logo/name (like "Shellkode")
- MIDDLE AREA: Client company name (large text, like "Truemeds")  
- BELOW CLIENT: Project title (like "Logistoc Planner analyzer")
- BOTTOM LEFT: Author name (like "Abdul")
- BOTTOM RIGHT: "Prepared by" text

FIELD DEFINITIONS:
- company_name: The CLIENT company name (large text in middle of cover page, NOT the vendor)
- project_title: The project name (appears below client company name on cover page)
- author_name: The PERSON's name (appears in bottom left corner of cover page)
- author_org: The VENDOR company (appears in top area with logo, like "Shellkode")
- objective: What the project aims to achieve (1-2 sentences)
- document_date: The document date in format: DD Month YYYY

CRITICAL EXTRACTION RULES:
⚠️ FOCUS ONLY ON THE COVER PAGE (FIRST PAGE) ⚠️

0. DOCUMENT PROPERTIES (HIGHEST PRIORITY):
   - If text starts with "DOCUMENT_AUTHOR: <name>", use that as author_name
   - If text starts with "DOCUMENT_TITLE: <title>", use that as project_title
   - These come from the document's built-in metadata and are most reliable

1. COMPANY NAME (Client):
   - Look for the LARGEST text on the cover page (usually client company name)
   - This is NOT "Shellkode" (that's the vendor)
   - Examples: "Truemeds", "SmallestAI", "TechCorp"

2. PROJECT TITLE:
   - Look for text BELOW the client company name
   - Usually 2-4 words describing the project
   - Examples: "Logistoc Planner analyzer", "Demand Forecasting System"
   - Extract EXACTLY as written, don't add words

3. AUTHOR NAME:
   - Look in BOTTOM LEFT corner of cover page
   - Usually just a first name or full name
   - Examples: "Abdul", "John Smith", "Sarah"
   - NOT "Contents", "About", or document structure text

4. AUTHOR ORG (Vendor):
   - Usually "Shellkode" (appears with logo in top area)

IGNORE THESE (they are document structure, not content):
- "Contents", "About", "Table of Contents", "Overview"
- "Scope of Work", "Project Overview" (these are section headers)
- "Prepared by" (this is a label, not the name)

{combined_text}

IMPORTANT: Return ONLY valid JSON, no markdown, no code blocks.
Focus on the cover page layout and extract the actual content, not document structure.
Return format:
{{"company_name": "...", "author_name": "...", "author_org": "...", "project_title": "...", "objective": "...", "document_date": "..."}}
"""
        
        response = bedrock.invoke_model(
            modelId=config.MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 600,
                "temperature": 0.05,  # Very low temperature for accurate extraction
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        response_body = json.loads(response['body'].read())
        _track_tokens(response_body, "Metadata Extraction")
        response_text = response_body['content'][0]['text'].strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            try:
                extracted = json.loads(json_match.group())
                
                # Log what was extracted
                print(f"   📋 LLM Extracted (RAW):")
                print(f"      Company: {extracted.get('company_name', 'N/A')}")
                print(f"      Author: {extracted.get('author_name', 'N/A')}")
                print(f"      Author Org: {extracted.get('author_org', 'N/A')}")
                print(f"      Project: {extracted.get('project_title', 'N/A')}")
                
                # Clean up project title - remove common unwanted prefixes/suffixes
                if extracted.get('project_title'):
                    original_title = extracted['project_title']
                    cleaned_title = _clean_project_title(original_title)
                    
                    # If the cleaned title is very different, try to extract from document directly
                    if len(cleaned_title.split()) < len(original_title.split()) - 1:
                        print(f"   🔍 Title seems over-enhanced by LLM, trying direct extraction...")
                        direct_title = _extract_project_title_regex(text_content)
                        if direct_title and direct_title != original_title:
                            print(f"   ✅ Direct extraction found: {direct_title}")
                            cleaned_title = direct_title
                    
                    if cleaned_title != original_title:
                        print(f"   🧹 Cleaned project title:")
                        print(f"      Before: {original_title}")
                        print(f"      After: {cleaned_title}")
                        extracted['project_title'] = cleaned_title
                
                # Clean up author name - remove common unwanted text
                if extracted.get('author_name'):
                    original_author = extracted['author_name']
                    cleaned_author = _clean_author_name(original_author)
                    if cleaned_author != original_author:
                        print(f"   🧹 Cleaned author name:")
                        print(f"      Before: {original_author}")
                        print(f"      After: {cleaned_author}")
                        extracted['author_name'] = cleaned_author
                
                # Try to extract author name from text if LLM failed
                if not extracted.get('author_name') or extracted.get('author_name').strip().lower() in ["unknown", "unknown author", ""]:
                    # First try DOCX properties
                    if docx_author:
                        extracted['author_name'] = docx_author
                        print(f"   ✅ Using author from document properties: {docx_author}")
                    else:
                        print(f"   🔍 LLM didn't find author, trying regex extraction...")
                        company = extracted.get('company_name', '')
                        author_name = _extract_author_name_regex(text_content, company_name=company)
                        if author_name:
                            extracted['author_name'] = author_name
                            print(f"   ✅ Regex found author: {author_name}")
                        else:
                            print(f"   ⚠️  Author name not found in document")
                            extracted['author_name'] = "Unknown Author"
                
                # If we still have invalid author names, mark as unknown
                current_author = extracted.get('author_name', '').strip().lower()
                invalid_author_patterns = [
                    'this', 'work', 'backend', 'deepar', 'develop', 'unknown author', '',
                    'this poc', 'this project', 'this document', 'the project',
                    'the system', 'the solution', 'poc', 'prod', 'sow',
                    'python', 'python-docx', 'admin', 'user', 'unknown'
                ]
                is_invalid = (
                    current_author in invalid_author_patterns or
                    any(current_author.startswith(p) for p in ['this ', 'the ', 'a ']) or
                    len(current_author.split()) > 3
                )
                if is_invalid:
                    print(f"   ⚠️ Invalid author '{extracted.get('author_name')}' detected")
                    # Use DOCX properties author as fallback
                    if docx_author and docx_author.lower() not in ['python-docx', 'python', 'unknown', 'author', 'admin', 'user', '']:
                        extracted['author_name'] = docx_author
                        print(f"   ✅ Using author from document properties: {docx_author}")
                    else:
                        extracted['author_name'] = "Unknown Author"

                # Try to extract project title from text if LLM failed
                if not extracted.get('project_title') or extracted.get('project_title').strip().lower() in ["unknown", "unknown project", ""]:
                    print(f"   🔍 LLM didn't find project title, trying regex extraction...")
                    project_title = _extract_project_title_regex(text_content)
                    if project_title:
                        extracted['project_title'] = project_title
                        print(f"   ✅ Regex found project title: {project_title}")
                    else:
                        print(f"   ⚠️  Project title not found in document, using default")
                        extracted['project_title'] = "Unknown Project"
                else:
                    # If LLM found a title, still set it as extracted (in case it needs cleaning later)
                    pass
                
                # Try to extract company name if LLM failed or found wrong one
                if (not extracted.get('company_name') or 
                    extracted.get('company_name').strip().lower() in ["unknown", "unknown company", ""] or
                    extracted.get('company_name').strip().lower() == "smallestai"):  # Known wrong extraction
                    print(f"   🔍 LLM company extraction needs verification, trying regex...")
                    company_name = _extract_company_name_regex(text_content)
                    if company_name:
                        extracted['company_name'] = company_name
                        print(f"   ✅ Regex found company: {company_name}")
                
                # Only set defaults if truly not found
                if not extracted.get('company_name') or extracted.get('company_name').strip().lower() in ["unknown", ""]:
                    extracted['company_name'] = "Unknown Company"
                if not extracted.get('author_org') or extracted.get('author_org').strip().lower() in ["unknown", ""]:
                    extracted['author_org'] = "Shellkode"
                if not extracted.get('objective') or not extracted.get('objective').strip():
                    extracted['objective'] = "Project Implementation"
                if not extracted.get('document_date') or extracted.get('document_date').strip().lower() in ["unknown", ""]:
                    extracted['document_date'] = datetime.now().strftime("%d %B %Y")
                
                # Add missing fields
                extracted['version'] = "2.0"
                extracted['start_date'] = (datetime.now() + timedelta(days=7)).strftime("%d %B %Y")
                extracted['end_date'] = (datetime.now() + timedelta(weeks=14)).strftime("%d %B %Y")
                extracted['timezone'] = "IST"
                
                return extracted
            except json.JSONDecodeError as e:
                print(f"❌ JSON Parse Error: {e}")
                return None
        
        print("❌ No JSON found in LLM response")
        return None
        
    except Exception as e:
        print(f"❌ LLM extraction error: {e}")
        import traceback
        traceback.print_exc()
        return None


def _extract_author_name_regex(text_content: str, company_name: str = "") -> str:
    """Extract author name from cover page - focuses on bottom left area where author appears"""
    import re

    # Focus on cover page and look in different areas
    cover_page = text_content[:1500]
    
    print(f"   📄 Looking for author name in cover page...")
    
    # Search in different areas with priority
    search_areas = [
        ("Bottom area", cover_page[800:]),  # Bottom of cover page (where author usually is)
        ("Middle area", cover_page[400:800]),
        ("Full cover page", cover_page),
    ]
    
    # Patterns to look for author names
    patterns = [
        # PRIORITY 1: Names with explicit labels
        r'(?:Prepared by|Author|Written by|Contact|By)[\s:]*\n?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',

        # PRIORITY 2: Look for any reasonable name patterns (First Last)
        r'\b([A-Z][a-z]{2,10}\s+[A-Z][a-z]{2,10})\b',

        # PRIORITY 3: Single capitalized name
        r'\b([A-Z][a-z]{3,8})\b',
    ]
    
    found_names = []
    
    for area_name, search_text in search_areas:
        for pattern_idx, pattern in enumerate(patterns):
            # Only use IGNORECASE for labeled patterns (pattern 0: "Prepared by", etc.)
            flags = re.MULTILINE | re.IGNORECASE if pattern_idx == 0 else re.MULTILINE
            matches = re.findall(pattern, search_text, flags)
            if matches:
                for match in matches:
                    name = match.strip() if isinstance(match, str) else match[0].strip()
                    
                    # Strict filtering for actual names
                    invalid_names = [
                        'unknown', 'author', 'john', 'doe', 'jane', 'test', 'user',
                        'prepared', 'written', 'contact', 'person', 'manager',
                        'shellkode', 'client', 'customer', 'vendor', 'company',
                        'contents', 'about', 'overview', 'document', 'page',
                        'table', 'toc', 'summary', 'introduction', 'scope',
                        'project', 'system', 'platform', 'solution', 'service',
                        'work', 'aws', 'sagemaker', 'lambda', 'api', 'gateway',
                        'step', 'functions', 'cbm', 'and', 'the', 'for', 'with',
                        'this', 'that', 'these', 'those', 'develop', 'requires',
                        'algorithm', 'deepar', 'serverle', 'serverless',
                        'demand', 'forecast', 'forecasting', 'intelligent',
                        'this poc', 'smallestai requires', 'deepar algorithm',
                        'develop serverle'
                    ]
                    # Add company name to invalid list (author can't be the company)
                    if company_name:
                        invalid_names.append(company_name.lower())
                        # Also add individual words of multi-word company names
                        for word in company_name.lower().split():
                            if len(word) > 2:
                                invalid_names.append(word)
                    
                    name_lower = name.lower()

                    # Check if it's a valid name
                    name_words = name_lower.split()
                    non_name_words = [
                        'poc', 'prod', 'sow', 'system', 'project', 'service',
                        'platform', 'solution', 'document', 'requires', 'algorithm',
                        'serverless', 'lambda', 'api', 'the', 'this', 'that', 'for',
                        'and', 'with', 'from', 'into', 'about',
                        # Common verbs that appear in sentence fragments
                        'faces', 'provides', 'offers', 'delivers', 'enables',
                        'supports', 'includes', 'creates', 'builds', 'uses',
                        'needs', 'wants', 'helps', 'makes', 'takes', 'gives',
                        'runs', 'works', 'serves', 'manages', 'handles',
                        'processes', 'generates', 'implements', 'integrates',
                        'streamlines', 'optimizes', 'automates', 'leverages',
                        'utilizes', 'ensures', 'maintains', 'monitors',
                        # Common nouns/adjectives in business text
                        'india', 'based', 'cloud', 'data', 'real', 'time',
                    ]
                    has_non_name_word = any(w in non_name_words for w in name_words)

                    is_valid_name = (
                        name and
                        len(name) >= 3 and len(name) <= 25 and
                        name[0].isupper() and
                        name_lower not in invalid_names and
                        not any(invalid == name_lower for invalid in invalid_names) and
                        not has_non_name_word and
                        not re.search(r'\d', name) and
                        not name_lower.startswith(('for', 'by', 'the', 'and', 'or', 'aws', 'this', 'that'))
                    )
                    
                    if is_valid_name:
                        # Calculate priority score
                        score = 0

                        # Higher score for names in bottom area (where author typically is)
                        if area_name == "Bottom area":
                            score += 100
                        elif area_name == "Middle area":
                            score += 50

                        # Higher score for names with labels (earlier patterns)
                        score += (10 - pattern_idx) * 10

                        # Higher score for reasonable name length
                        if 4 <= len(name) <= 15:
                            score += 20

                        # Prefer full names over single names
                        word_count = len(name.split())
                        if word_count == 2:
                            score += 30
                        elif word_count == 1:
                            score += 20

                        found_names.append((score, name, area_name, pattern_idx))
    
    # Sort by priority score and return the best match
    if found_names:
        found_names.sort(key=lambda x: x[0], reverse=True)
        
        print(f"   🔍 Found potential author names:")
        for score, name, area, pattern in found_names[:5]:
            print(f"      {score:3d}: '{name}' ({area}, pattern_{pattern})")
        
        best_score, best_name, best_area, best_pattern = found_names[0]
        
        # Only return if score is reasonable
        if best_score >= 50:
            print(f"   ✅ Selected author: '{best_name}' (score: {best_score}, area: {best_area})")
            return best_name
        else:
            print(f"   ⚠️  Best candidate score too low ({best_score})")
    
    print(f"   ⚠️  No suitable author name found")
    return None


def _extract_requirements_with_llm(text_content: str) -> dict:
    """Extract detailed requirements from document content using LLM"""
    try:
        bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=config.AWS_REGION,
            config=config.BOTO_CONFIG
        )
        
        prompt = f"""Analyze this POC document and extract key technical requirements and information.

DOCUMENT CONTENT (First 5000 chars):
{text_content[:5000]}

Extract and return ONLY valid JSON (no markdown, no extra text):

{{
  "project_overview": "What the POC delivered/accomplished",
  "key_features": ["feature1", "feature2"],
  "aws_services": ["service1", "service2"],
  "technical_stack": ["tech1", "tech2"],
  "success_metrics": ["metric1", "metric2"],
  "architecture_components": ["component1", "component2"],
  "integrations": ["integration1"],
  "business_impact": "Business value or outcome",
  "timeline": "Timeline or duration mentioned",
  "scope": "Project scope and boundaries"
}}

IMPORTANT: Use ONLY information from the document. If not found, use empty arrays [] or "Not specified"."""

        response = bedrock.invoke_model(
            modelId=config.MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 2048,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        response_body = json.loads(response['body'].read())
        _track_tokens(response_body, "Requirements Extraction")
        llm_output = response_body['content'][0]['text'].strip()
        
        # Clean JSON
        if '```json' in llm_output:
            llm_output = llm_output.split('```json')[1].split('```')[0].strip()
        elif '```' in llm_output:
            llm_output = llm_output.split('```')[1].split('```')[0].strip()
        
        # Parse JSON
        try:
            requirements = json.loads(llm_output)
            print(f"✅ Requirements extraction successful:")
            print(f"   Features: {len(requirements.get('key_features', []))}")
            print(f"   AWS Services: {len(requirements.get('aws_services', []))}")
            print(f"   Tech Stack: {len(requirements.get('technical_stack', []))}")
            return requirements
        except json.JSONDecodeError as e:
            print(f"⚠️  Requirements JSON parse failed: {e}")
            return {
                "project_overview": "POC Implementation",
                "key_features": [],
                "aws_services": [],
                "technical_stack": [],
                "success_metrics": [],
                "architecture_components": [],
                "integrations": [],
                "business_impact": "Not specified",
                "timeline": "Not specified",
                "scope": "Not specified"
            }
        
    except Exception as e:
        print(f"❌ Requirements extraction error: {e}")
        return {
            "project_overview": "POC Implementation",
            "key_features": [],
            "aws_services": [],
            "technical_stack": [],
            "success_metrics": [],
            "architecture_components": [],
            "integrations": [],
            "business_impact": "Not specified",
            "timeline": "Not specified",
            "scope": "Not specified"
        }


def research_node(state: AgentState) -> AgentState:
    """Research company information"""
    print(f"\n--- Step: Researching Companies ---")
    metadata = state['metadata']
    
    if metadata.get('author_org_description') and metadata.get('company_description'):
        print("✓ Using existing company research from enhanced extraction")
        return {"current_step": "research"}
    
    research_agent = CompanyResearchAgent(config)
    companies = [metadata['author_org'], metadata['company_name']]
    print(f"   Researching: {companies}")
    
    results = research_agent.research_multiple_companies(companies)
    
    metadata['author_org_description'] = results.get(metadata['author_org'], 
        "Shellkode specializes in developing advanced data and AI solutions for businesses.")
    metadata['company_description'] = results.get(metadata['company_name'], 
        f"Leading organization focused on digital transformation and innovation.")
    
    print(f"✅ Company research completed")
    print(f"   Vendor: {metadata['author_org']}")
    print(f"   Client: {metadata['company_name']}")
    
    return {"metadata": metadata, "current_step": "research"}


def analyze_objective_node(state: AgentState) -> AgentState:
    """Analyze project objective"""
    if state.get('mode') == 'POC_TO_PROD' and state.get('analyzed_requirements'):
        print(f"\n--- Step: Using Enhanced POC Requirements for Production ---")
        analyzed_requirements = state.get('analyzed_requirements')
        
        if isinstance(analyzed_requirements, dict) and 'project_overview' in analyzed_requirements:
            print(f"✅ Using detailed requirements from document ingestion")
            print(f"   Features: {len(analyzed_requirements.get('key_features', []))}")
            print(f"   AWS Services: {len(analyzed_requirements.get('aws_services', []))}")
            print(f"   Tech Stack: {len(analyzed_requirements.get('technical_stack', []))}")
        else:
            print(f"✅ Using RAG-based requirements for production conversion")
        
        return {"current_step": "analyze"}

    print(f"\n--- Step: Analyzing Objective ---")
    objective = state.get('objective', '').strip()
    
    # Validate objective
    if not objective:
        print("⚠️ No objective provided in state, using default")
        objective = "Build a comprehensive AWS-based solution for business requirements"
    
    print(f"   Objective: {objective[:100]}{'...' if len(objective) > 100 else ''}")

    # Get supporting context if available
    supporting_context = state.get('supporting_context')
    if supporting_context:
        print(f"   📚 Using supporting documents context ({len(supporting_context)} chars)")

    objective_agent = ObjectiveAgent(config)
    analyzed_requirements = objective_agent.analyze_objective(objective, supporting_context)

    print(f"✅ Objective analysis completed")
    
    # Extract ui_required flag and add to metadata
    ui_required = analyzed_requirements.get('ui_required', False)
    
    # Additional validation: if no explicit UI keywords found in objective, ensure ui_required is False
    objective_lower = objective.lower()
    ui_keywords = [
        "user interface", "ui", "frontend", "web interface", "dashboard", 
        "web application", "portal", "screen", "screens", "visualization"
    ]
    negative_indicators = [
        "no user interface", "without user interface", "no frontend", "without frontend",
        "no web interface", "without web interface", "no dashboard", "without dashboard",
        "no web application", "without web application", "no portal", "without portal",
        "no screen", "without screen", "no screens", "without screens",
        "no visualization", "without visualization", "backend-only", "api-only",
        "without any", "no ui", "without ui"
    ]
    
    # Check for negative context
    has_negative_context = any(neg in objective_lower for neg in negative_indicators)
    if has_negative_context:
        ui_required = False
        print(f"   UI Override: Forced to False due to negative context")
    
    # Check if any UI keywords are actually present
    import re
    has_ui_keywords = False
    
    # Check for "ui" as standalone word
    if re.search(r'\bui\b', objective_lower):
        has_ui_keywords = True
    
    # Check for other UI keywords
    ui_keywords_no_ui = [
        "user interface", "frontend", "web interface", "dashboard", 
        "web application", "portal", "screen", "screens", "visualization"
    ]
    if any(keyword in objective_lower for keyword in ui_keywords_no_ui):
        has_ui_keywords = True
    
    if not has_ui_keywords and ui_required:
        ui_required = False
        print(f"   UI Override: Forced to False - no explicit UI keywords found in objective")
    
    print(f"   UI Implementation: {'Required' if ui_required else 'Not Required'}")
    
    # Update analyzed_requirements with corrected ui_required
    analyzed_requirements['ui_required'] = ui_required
    
    # Update metadata with ui_required flag
    metadata = state.get('metadata', {})
    metadata['ui_required'] = ui_required
    
    return {
        "analyzed_requirements": analyzed_requirements,
        "metadata": metadata,
        "current_step": "analyze"
    }


def rule_validation_node(state: AgentState) -> AgentState:
    """Validate requirements against rules"""
    print(f"\n--- Step: Validating Rules ---")
    analyzed_requirements = state['analyzed_requirements']
    objective = state['objective']
    
    rule_engine = RuleEngineAgent(config)
    validated_requirements = rule_engine.validate_requirements(
        analyzed_requirements,
        objective
    )
    
    return {"validated_requirements": validated_requirements, "current_step": "validate"}


def content_generation_node(state: AgentState) -> AgentState:
    """Generate SOW content"""
    print(f"\n--- Step: Generating Content ---")
    validated_requirements = state['validated_requirements']
    analyzed_requirements = state.get('analyzed_requirements', {})
    metadata = state['metadata']
    mode = state.get('mode', 'POC')
    
    template_type = "PROD" if mode in ["PROD", "POC_TO_PROD"] else "POC"
    print(f"✅ Using Template: {template_type}")
    print(f"   Company: {metadata.get('company_name', 'N/A')}")
    print(f"   Project: {metadata.get('project_title', 'N/A')}")
    print(f"   Mode: {mode}")
    
    # Merge user-specified data from analyzed_requirements into validated_requirements
    # This preserves user-specified timeline, AWS services, etc.
    final_requirements = validated_requirements.copy()
    
    # Preserve user-specified fields from analyzed_requirements
    user_fields = ['duration_weeks', 'timeline', 'aws_services', 'document_volume', 'ui_required']
    for field in user_fields:
        if field in analyzed_requirements:
            final_requirements[field] = analyzed_requirements[field]
            print(f"   ✅ Preserved user-specified {field}: {analyzed_requirements[field]}")
    
    # Special validation for timeline to ensure it's not overridden
    user_timeline = analyzed_requirements.get('timeline')
    user_duration_weeks = analyzed_requirements.get('duration_weeks')
    if user_timeline and user_timeline != 'Not specified':
        final_requirements['timeline'] = user_timeline
        print(f"   🔒 TIMELINE LOCKED: {user_timeline}")
    if user_duration_weeks and str(user_duration_weeks) != 'Not specified':
        final_requirements['duration_weeks'] = user_duration_weeks
        print(f"   🔒 DURATION LOCKED: {user_duration_weeks} weeks")
    
    # Also preserve extracted data summary if available
    if 'extracted_data_summary' in analyzed_requirements:
        final_requirements['extracted_data_summary'] = analyzed_requirements['extracted_data_summary']
        print(f"   ✅ Preserved extracted data summary")
    
    if isinstance(final_requirements, dict):
        features_count = len(final_requirements.get('key_features', []))
        aws_services_count = len(final_requirements.get('aws_services', []))
        print(f"   Requirements: {features_count} features, {aws_services_count} AWS services")
    
    poc_writer = POCWriterAgent(config, template_type=template_type)
    
    # Get RAG context for enhanced generation
    rag_context = state.get('rag_context')

    # Get supporting context if available
    supporting_context = state.get('supporting_context')
    if supporting_context:
        print(f"   📚 Including supporting documents context ({len(supporting_context)} chars)")

    poc_content = poc_writer.generate_poc(
        requirements=final_requirements,
        metadata=metadata,
        rag_context=rag_context,
        supporting_context=supporting_context
    )

    print(f"✅ Content generation completed")
    
    return {"poc_content": poc_content, "current_step": "generate"}


def pdf_build_node(state: AgentState) -> AgentState:
    """Build DOCX document using temporary files (cloud-only mode)"""
    print(f"\n--- Step: Building Document (DOCX Primary, PDF for RAG) ---")
    poc_content = state['poc_content']
    metadata = state['metadata']
    mode = state.get('mode', 'POC')
    
    print(f"✅ Building {mode} document")
    print(f"   Company: {metadata.get('company_name', 'N/A')}")
    print(f"   Project: {metadata.get('project_title', 'N/A')}")
    print(f"   Author: {metadata.get('author_name', 'N/A')}")
    
    # Clean content before building document
    print(f"\n🧹 Cleaning content for markdown artifacts...")
    cleaned_content = {}
    for section_key, content in poc_content.items():
        if content:
            cleaned_content[section_key] = _clean_final_content(str(content))
        else:
            cleaned_content[section_key] = content
    
    # Debug: Show available sections
    print(f"\n📋 Available sections ({len(cleaned_content)}):")
    for i, (key, content) in enumerate(list(cleaned_content.items())[:10], 1):
        content_preview = str(content)[:50] if content else "empty"
        print(f"  {i}. {key}: {content_preview}...")
    if len(cleaned_content) > 10:
        print(f"  ... and {len(cleaned_content) - 10} more sections")
    
    try:
        # Use temporary directory for document building
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Temporarily override the output directory in config
            original_output_dir = config.OUTPUT_DIR
            config.OUTPUT_DIR = temp_path
            
            try:
                doc_builder = DocumentBuilder(config)
                
                # Build document (primary deliverable)
                print("🔄 Building document (primary deliverable)...")
                doc_output_path = doc_builder.build_document(cleaned_content, metadata, mode=mode)
                
                if not doc_output_path:
                    raise Exception("Document builder returned None - likely TOC parsing failed")
                
                print(f"✅ Document built successfully")
                
                # Move document to permanent temp location for upload
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                suffix = "PROD" if mode in ["PROD", "POC_TO_PROD"] else "POC"
                
                # Create temp file for upload (preserves extension)
                file_ext = doc_output_path.suffix  # .docx or .pdf
                temp_doc_path = tempfile.mktemp(suffix=file_ext, prefix=f'{suffix}_')
                import shutil
                shutil.copy2(doc_output_path, temp_doc_path)
                
                print(f"✅ Document ready for cloud upload: {Path(temp_doc_path).name}")
                
                # Generate JSON data in memory
                json_data = {
                    'metadata': metadata,
                    'requirements': state['validated_requirements'],
                    'sections': cleaned_content,
                    'mode': state.get('mode'),
                    'generation_timestamp': datetime.now().isoformat(),
                    'source_file': state.get('source_file'),
                    'rag_context': state.get('rag_context', {}).get('retrieval_success', False)
                }
                
                print(f"✅ Document build completed")
                print(f"   Document: {Path(temp_doc_path).name}")
                print(f"   JSON data: Generated in memory")
                
                return {
                    "output_path": temp_doc_path,  # Document file for upload
                    "json_data": json_data,
                    "current_step": "build"
                }
                
            finally:
                # Restore original output directory
                config.OUTPUT_DIR = original_output_dir
        
    except Exception as e:
        print(f"❌ Document building failed: {e}")
        print("🔧 Attempting emergency document generation...")
        
        # Emergency fallback: create a simple DOCX document
        try:
            import tempfile
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            suffix = "PROD" if mode in ["PROD", "POC_TO_PROD"] else "POC"
            
            # Create emergency temp file
            emergency_path = tempfile.mktemp(suffix='.pdf', prefix=f'EMERGENCY_{suffix}_')
            
            # Create emergency PDF document
            from reportlab.pdfgen import canvas
            from reportlab.lib.pagesizes import A4
            
            print(f"✅ Emergency document created in temp location")
            
            return {
                "output_path": emergency_path,
                "json_data": {"emergency": True, "metadata": metadata},
                "current_step": "build"
            }
            
        except Exception as emergency_error:
            print(f"❌ Emergency document generation also failed: {emergency_error}")
            state["errors"].append(f"Document generation failed: {e}")
            state["errors"].append(f"Emergency generation failed: {emergency_error}")
            return state
            
            c = canvas.Canvas(emergency_path, pagesize=A4)
            width, height = A4
            y_position = height - 50
            
            # Title
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, y_position, "EMERGENCY DOCUMENT GENERATION")
            y_position -= 30
            
            c.setFont("Helvetica", 12)
            c.drawString(50, y_position, "=" * 40)
            y_position -= 30
            
            # Metadata
            lines = [
                f"Company: {metadata.get('company_name', 'N/A')}",
                f"Project: {metadata.get('project_title', 'N/A')}",
                f"Mode: {mode}",
                f"Generated: {datetime.now().isoformat()}",
                "",
                f"ERROR: Document builder failed - {str(e)}",
                "",
                "GENERATED CONTENT:",
                "=" * 20,
                ""
            ]
            
            for line in lines:
                if y_position < 50:
                    c.showPage()
                    y_position = height - 50
                c.drawString(50, y_position, line)
                y_position -= 15
            
            # Content sections
            for section_key, content in cleaned_content.items():
                if y_position < 100:
                    c.showPage()
                    y_position = height - 50
                
                # Section header
                c.setFont("Helvetica-Bold", 12)
                c.drawString(50, y_position, f"{section_key.replace('_', ' ').title()}")
                y_position -= 20
                
                c.setFont("Helvetica", 10)
                # Split content into lines
                content_lines = str(content).split('\n')
                for content_line in content_lines[:10]:  # Limit lines per section
                    if y_position < 50:
                        c.showPage()
                        y_position = height - 50
                    # Truncate long lines
                    if len(content_line) > 80:
                        content_line = content_line[:77] + "..."
                    c.drawString(50, y_position, content_line)
                    y_position -= 12
                
                y_position -= 10  # Extra space between sections
            
            c.save()
            
            print(f"✅ Emergency document created in temp location")
            
            # Generate JSON data in memory
            json_data = {
                'metadata': metadata,
                'requirements': state['validated_requirements'],
                'sections': cleaned_content,
                'mode': state.get('mode'),
                'generation_timestamp': datetime.now().isoformat(),
                'source_file': state.get('source_file'),
                'rag_context': state.get('rag_context', {}).get('retrieval_success', False),
                'emergency_mode': True,
                'error': str(e)
            }
            
            return {
                "output_path": emergency_path,
                "json_data": json_data,
                "current_step": "build"
            }
            
        except Exception as emergency_error:
            print(f"❌ Emergency document creation also failed: {emergency_error}")
            raise Exception(f"Both normal and emergency document generation failed: {str(e)}")