"""
Enhanced Document Reader - With OCR Support for Image-Heavy Documents
MAINTAINS BACKWARD COMPATIBILITY WITH ORIGINAL FUNCTION NAMES
Handles: PDF, DOCX (text & image-based), TXT
"""
import os
import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from pypdf import PdfReader
import docx
from docx.document import Document as _DocumentType
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
import zipfile
import io

# Optional: For OCR support (install with: pip install pytesseract pillow)
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️  pytesseract/Pillow not installed. OCR features disabled.")
    print("   Install with: pip install pytesseract pillow")


def read_document(file_path: str) -> str:
    """
    Read content from PDF or DOCX file
    Extracts ALL content including paragraphs, tables, headers, footers
    
    BACKWARD COMPATIBLE - Same function signature as original
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
        
    ext = os.path.splitext(file_path)[1].lower()
    
    print(f"📖 Reading file: {Path(file_path).name} ({ext.upper()})")
    
    if ext == '.pdf':
        content = _read_pdf(file_path)
    elif ext in ['.docx', '.doc']:
        content = _read_docx(file_path)
    elif ext == '.txt':
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        raise ValueError(f"Unsupported file format: {ext}")
    
    # Validate extraction
    if not content or len(content.strip()) < 50:
        print(f"⚠️  WARNING: Extracted content is very small ({len(content)} chars)")
        print(f"   This may indicate extraction failed")
    
    return content


def _read_pdf(file_path: str) -> str:
    """
    Extract text from PDF
    Handles multi-page PDFs and scanned PDFs with OCR fallback
    """
    try:
        reader = PdfReader(file_path)
        num_pages = len(reader.pages)
        print(f"   📄 PDF has {num_pages} pages")
        
        text_parts = []
        image_based_count = 0
        
        for page_num, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(f"\n--- Page {page_num + 1} ---\n")
                text_parts.append(page_text)
            else:
                # Page has no text - likely image-based
                image_based_count += 1
                if OCR_AVAILABLE:
                    print(f"   🖼️  Page {page_num + 1} appears to be image-based, attempting OCR...")
                    ocr_text = _extract_images_from_pdf_page(page)
                    if ocr_text:
                        text_parts.append(f"\n--- Page {page_num + 1} (OCR) ---\n")
                        text_parts.append(ocr_text)
                else:
                    text_parts.append(f"\n--- Page {page_num + 1} (No text/OCR disabled) ---\n")
        
        text = "".join(text_parts)
        print(f"   ✓ Extracted {len(text)} characters from {num_pages} pages")
        if image_based_count > 0:
            print(f"   ℹ️  Found {image_based_count} image-based pages")
        
        return text
    
    except Exception as e:
        print(f"❌ Error reading PDF: {e}")
        raise


def _iter_docx_blocks(document):
    """Yield paragraphs and tables in their actual document-body order."""
    parent = document.element.body
    for child in parent.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def _read_docx(file_path: str) -> str:
    """
    Extract ALL content from DOCX file
    ENHANCED VERSION - handles complex document structures
    Includes:
    - Paragraphs (including nested content)
    - Tables (with proper cell extraction)
    - Headers and footers
    - Text boxes and shapes (where possible)
    - Image-based DOCX with OCR fallback
    """
    try:
        doc = docx.Document(file_path)
        text_parts = []

        print(f"   📋 Extracting headers, paragraphs, tables, and other content...")

        # Extract DOCX core properties (author, title, etc.)
        try:
            props = doc.core_properties
            props_parts = []
            # Filter out default/invalid property values
            invalid_authors = ['python-docx', 'python', 'unknown', 'author', 'user', 'admin', '']
            if props.author and props.author.strip().lower() not in invalid_authors:
                props_parts.append(f"DOCUMENT_AUTHOR: {props.author}")
                print(f"   ✓ Found document author in properties: {props.author}")
            if props.title and props.title.strip().lower() not in ['word document', 'document', '']:
                props_parts.append(f"DOCUMENT_TITLE: {props.title}")
            if props.subject and props.subject.strip():
                props_parts.append(f"DOCUMENT_SUBJECT: {props.subject}")
            if props_parts:
                text_parts.extend(props_parts)
        except Exception as props_e:
            print(f"   ⚠️  Could not read core properties: {props_e}")

        # Check if document is primarily image-based
        image_count = _count_images_in_docx(file_path)
        has_text = len(doc.paragraphs) > 0 and any(p.text.strip() for p in doc.paragraphs)
        
        # If no text found but images exist, try OCR
        if not has_text and image_count > 0 and OCR_AVAILABLE:
            print(f"   🖼️  Document appears to be image-based ({image_count} images found)")
            print(f"   🔍 Using OCR to extract text from images...")
            ocr_content = _extract_images_from_docx_ocr(file_path)
            if ocr_content:
                return ocr_content
        
        # 1. Extract from headers and footers
        for section in doc.sections:
            # Header
            if section.header:
                for para in section.header.paragraphs:
                    if para.text.strip():
                        text_parts.append(f"HEADER: {para.text.strip()}")
            
            # Footer
            if section.footer:
                for para in section.footer.paragraphs:
                    if para.text.strip():
                        text_parts.append(f"FOOTER: {para.text.strip()}")
        
        # 2. Extract paragraphs and tables in source order.  The previous reader
        # appended every table after every paragraph and globally de-duplicated
        # lines, which destroyed context and legitimate repeated requirements.
        table_idx = 0
        for block in _iter_docx_blocks(doc):
            if isinstance(block, Paragraph):
                para_text = block.text.strip()
                if para_text:
                    style = block.style.name if block.style is not None else ""
                    if style.lower().startswith("heading"):
                        text_parts.append(f"HEADING: {para_text}")
                    else:
                        text_parts.append(para_text)
            else:
                table_text = _extract_table_content_enhanced(block, table_idx)
                table_idx += 1
                if table_text.strip():
                    text_parts.append(table_text)

        final_text = "\n".join(part.strip() for part in text_parts if part and part.strip())
        
        print(f"   ✓ Extracted {len(final_text)} characters from DOCX")
        print(f"   ✓ Found {len(doc.paragraphs)} paragraphs, {len(doc.tables)} tables")
        
        if len(final_text) < 100:
            print(f"   ⚠️  Content seems small, preview:")
            print(f"      {final_text[:300]}")
        
        return final_text
    
    except Exception as e:
        print(f"❌ Error reading DOCX: {e}")
        import traceback
        traceback.print_exc()
        raise


def _extract_table_content_enhanced(table, table_idx: int) -> str:
    """
    Enhanced table content extraction
    
    Args:
        table: python-docx table object
        table_idx: Table index for identification
        
    Returns:
        str: Formatted table content with better structure
    """
    table_parts = []
    table_parts.append(f"\n--- TABLE {table_idx + 1} ---")
    
    for row_idx, row in enumerate(table.rows):
        row_data = []
        for cell_idx, cell in enumerate(row.cells):
            # Extract all content from cell including nested paragraphs
            cell_content = []
            
            for para in cell.paragraphs:
                para_text = para.text.strip()
                if para_text:
                    cell_content.append(para_text)
            
            # Join cell content
            if cell_content:
                cell_text = " ".join(cell_content)
                row_data.append(cell_text)
            else:
                row_data.append("")
        
        if any(cell.strip() for cell in row_data):  # Only add non-empty rows
            # Format as key-value if it looks like a two-column table
            if len(row_data) == 2 and row_data[0] and row_data[1]:
                table_parts.append(f"{row_data[0]}: {row_data[1]}")
            else:
                # Multi-column table
                table_parts.append(" | ".join(row_data))
    
    table_parts.append("--- END TABLE ---\n")
    
    return "\n".join(table_parts) if len(table_parts) > 2 else ""


def extract_metadata_from_content(content: str) -> dict:
    """
    Extract potential metadata from document content
    Looks for common patterns, especially author name on cover page bottom right
    
    Args:
        content: Full document text
        
    Returns:
        dict: Extracted metadata
        
    ORIGINAL FUNCTION - UNCHANGED SIGNATURE
    """
    metadata = {
        "company_name": None,
        "project_title": None,
        "author_name": None,
        "author_org": None,
        "date": None
    }
    
    lines = content.split('\n')
    
    # PRIORITY: Extract author from cover page (first 150 lines, especially bottom portion)
    # Author is typically on the cover page at the right bottom corner
    cover_page_lines = lines[:150]
    
    # Pattern 1: Look for "For: Company Name" or "For:" or "Client:"
    for line in cover_page_lines:
        # Try exact "For:" match
        if re.search(r'^For:\s+(.+)', line, re.IGNORECASE):
            match = re.search(r'^For:\s+(.+)', line, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if company and len(company) > 3:
                    metadata["company_name"] = company
                    break
        # Try "Client:" match
        elif re.search(r'Client:\s+(.+)', line, re.IGNORECASE):
            match = re.search(r'Client:\s+(.+)', line, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                if company and len(company) > 3:
                    metadata["company_name"] = company
                    break
    
    # Pattern 2: Look for project title (usually a longer line with title case in first 50 lines)
    for line in cover_page_lines[0:50]:
        line = line.strip()
        # Skip common non-title lines
        if len(line) > 15 and not any(skip in line.lower() for skip in ['for:', 'prepared', 'date:', 'version', 'status']):
            # Check if it has title case pattern (starts with capital letter)
            if line and line[0].isupper():
                metadata["project_title"] = line
                break
    
    # Pattern 3: Look for "Prepared by:" or "Author:" - PRIORITIZE COVER PAGE
    # Check cover page first (where author is typically located at bottom right)
    for line in cover_page_lines:
        if re.search(r'Prepared\s+by:?\s*(.+)', line, re.IGNORECASE):
            match = re.search(r'Prepared\s+by:?\s*(.+)', line, re.IGNORECASE)
            if match:
                author = match.group(1).strip()
                if author and len(author) > 2 and author.lower() not in ['unknown', 'author']:
                    metadata["author_name"] = author
                    break
        elif re.search(r'Author:?\s+(.+)', line, re.IGNORECASE):
            match = re.search(r'Author:?\s+(.+)', line, re.IGNORECASE)
            if match:
                author = match.group(1).strip()
                if author and len(author) > 2 and author.lower() not in ['unknown', 'author']:
                    metadata["author_name"] = author
                    break
    
    # If author not found with label, look for name patterns on cover page
    if not metadata["author_name"]:
        # Look for capitalized names (First Last format) in the latter part of cover page
        # (bottom right corner area)
        for line in cover_page_lines[50:]:  # Focus on bottom portion
            # Match "First Last" name pattern
            name_match = re.search(r'\b([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b', line)
            if name_match:
                potential_name = name_match.group(1)
                # Validate it's not a common false positive
                invalid_names = ['table of', 'page number', 'document title', 'project manager', 
                                'contact person', 'company name', 'client name']
                if potential_name.lower() not in invalid_names:
                    metadata["author_name"] = potential_name
                    break
    
    # Pattern 4: Look for dates (DD Mon YYYY format)
    for line in cover_page_lines[:50]:
        date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})', line, re.IGNORECASE)
        if date_match:
            metadata["date"] = date_match.group(0)
            break
        # Try MM/DD/YYYY format
        date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', line)
        if date_match:
            metadata["date"] = date_match.group(0)
            break
    
    return metadata


def validate_extraction(content: str, file_path: str) -> bool:
    """
    Validate that extraction was successful
    
    Args:
        content: Extracted content
        file_path: Original file path
        
    Returns:
        bool: True if extraction seems valid
        
    ORIGINAL FUNCTION - UNCHANGED SIGNATURE
    """
    if not content or len(content.strip()) < 50:
        print(f"❌ Extraction validation failed: Content too small ({len(content)} chars)")
        return False
    
    # Check for some common text patterns
    lower_content = content.lower()
    
    # Look for common business document words
    doc_indicators = ['project', 'service', 'deliverable', 'timeline', 'scope', 'objective', 'requirement', 'aws', 'solution', 'document']
    found_indicators = sum(1 for word in doc_indicators if word in lower_content)
    
    if found_indicators == 0:
        print(f"⚠️  Warning: Document may not be a standard business document")
        print(f"   (None of these words found: {', '.join(doc_indicators)})")
        return False
    
    return True


# ============================================================================
# HELPER FUNCTIONS FOR OCR AND IMAGE PROCESSING
# ============================================================================

def _count_images_in_docx(file_path: str) -> int:
    """Count images embedded in DOCX"""
    try:
        with zipfile.ZipFile(file_path, 'r') as docx_zip:
            image_files = [f for f in docx_zip.namelist() if f.startswith('word/media/')]
            return len(image_files)
    except:
        return 0


def _extract_images_from_docx_ocr(file_path: str) -> str:
    """Extract text from images in DOCX using OCR"""
    if not OCR_AVAILABLE:
        return None
    
    try:
        extracted_text = []
        
        with zipfile.ZipFile(file_path, 'r') as docx_zip:
            media_files = [f for f in docx_zip.namelist() if f.startswith('word/media/')]
            
            print(f"   Processing {len(media_files)} images with OCR...")
            
            for idx, media_file in enumerate(sorted(media_files)):
                try:
                    image_data = docx_zip.read(media_file)
                    image = Image.open(io.BytesIO(image_data))
                    
                    print(f"   🔄 OCR processing image {idx + 1}/{len(media_files)}...")
                    text = pytesseract.image_to_string(image)
                    
                    if text.strip():
                        extracted_text.append(f"\n--- Image {idx + 1} ---\n{text}")
                
                except Exception as img_err:
                    print(f"   ⚠️  Could not process image {idx + 1}: {img_err}")
                    continue
        
        result = "\n".join(extracted_text)
        if result:
            print(f"   ✓ OCR extracted {len(result)} characters from {len(media_files)} images")
        return result
    
    except Exception as e:
        print(f"❌ OCR extraction failed: {e}")
        return None


def _extract_images_from_pdf_page(page):
    """Extract and perform OCR on images from PDF page"""
    if not OCR_AVAILABLE:
        return None
    
    try:
        import pdf2image
        images = pdf2image.convert_from_bytes(page.pdf_ref.stream_data)
        
        text_parts = []
        for img in images:
            text = pytesseract.image_to_string(img)
            if text.strip():
                text_parts.append(text)
        
        return "\n".join(text_parts)
    except:
        return None


# Example usage
if __name__ == "__main__":
    # Use raw string (r"") to avoid escape sequence warnings
    try:
        file_path = r"D:\project\POC\POC_docx\Saafe _ AIOps _ SOW v1.0.docx"
        content = read_document(file_path)
        
        print("\n✓ Successfully extracted content!")
        print(f"\nPreview (first 500 chars):\n{content[:500]}")
        
        # Extract metadata
        metadata = extract_metadata_from_content(content)
        print(f"\nMetadata: {metadata}")
        
        # Validate
        is_valid = validate_extraction(content, file_path)
        print(f"\nValidation: {'✓ PASSED' if is_valid else '❌ FAILED'}")
        
    except FileNotFoundError as e:
        print(f"\n❌ File not found: {e}")
    except Exception as e:
        print(f"\n❌ Error: {e}")


def extract_supporting_documents(file_paths: list) -> str:
    """
    Extract and consolidate content from multiple supporting documents

    Args:
        file_paths: List of paths to supporting documents (PDF/DOCX/TXT)

    Returns:
        Consolidated text content from all supporting documents
    """
    if not file_paths:
        return ""

    print(f"\n📚 Processing {len(file_paths)} supporting document(s)...")
    print("="*70)

    consolidated_content = []
    successful_reads = 0

    for idx, file_path in enumerate(file_paths, 1):
        try:
            if not os.path.exists(file_path):
                print(f"⚠️  {idx}. Skipping missing file: {file_path}")
                continue

            # Read document content
            content = read_document(file_path)

            if content and len(content.strip()) > 10:
                file_name = Path(file_path).name
                consolidated_content.append(f"\n{'='*70}")
                consolidated_content.append(f"\nSUPPORTING DOCUMENT {idx}: {file_name}")
                consolidated_content.append(f"\n{'='*70}\n")
                consolidated_content.append(content)
                consolidated_content.append(f"\n{'='*70}\n")
                successful_reads += 1
                print(f"✓ {idx}. {file_name} - Extracted {len(content)} characters")
            else:
                print(f"⚠️  {idx}. {Path(file_path).name} - No content extracted")

        except Exception as e:
            print(f"❌ {idx}. Error reading {Path(file_path).name}: {e}")
            continue

    result = "\n".join(consolidated_content)
    print(f"\n✓ Successfully processed {successful_reads}/{len(file_paths)} documents")
    print(f"✓ Total consolidated content: {len(result)} characters")
    print("="*70 + "\n")

    return result
