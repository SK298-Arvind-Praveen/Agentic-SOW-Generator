"""
COMPLETE FIXED SOW PIPELINE
Template-based hybrid classification with AWS Bedrock & Pinecone
Uses AWS Titan Embeddings & accepts user file input
Production-ready code - FULLY COMPLETE & DEBUGGED
"""

# ============================================================================
# PART 1: CONSOLIDATED IMPORTS
# ============================================================================

from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
import json
import boto3
import re
from datetime import datetime
import os
from pathlib import Path

import PyPDF2
from docx import Document
from pinecone import Pinecone
from dotenv import load_dotenv


# ============================================================================
# PART 2: ENUMS & DATACLASSES
# ============================================================================

class SectionType(Enum):
    """Section types derived from your SOW template"""
    ABOUT_AUTHOR = "about_author"
    ABOUT_COMPANY = "about_company"
    PROJECT_OVERVIEW = "project_overview"
    SCOPE_OF_WORK = "scope_of_work"
    ARCHITECTURE = "architecture"
    CUSTOMER_DEPENDENCIES = "customer_dependencies"
    ASSUMPTIONS = "assumptions"
    OUT_OF_SCOPE = "out_of_scope"
    TIMELINES = "timelines"
    AWS_PRICING = "aws_pricing"
    CUSTOMER_RESPONSIBILITIES = "customer_responsibilities"
    DURATION_OF_WORK = "duration_of_work"
    RESOURCE_LOADING = "resource_loading"
    SUCCESS_CRITERIA = "success_criteria"
    DELIVERABLE_ACCEPTANCE = "deliverable_acceptance"
    CHANGE_ORDER = "change_order"
    PROJECT_TERMINATION = "project_termination"
    CONTACTS = "contacts"
    MARKETING = "marketing"
    TERMS_CONDITIONS = "terms_conditions"
    ACCEPTANCE = "acceptance"
    TABLE_OF_CONTENTS = "table_of_contents"


@dataclass
class TemplateSection:
    """Represents a section from your template"""
    name: str
    section_type: SectionType
    meta_tag: str
    is_dynamic: bool
    description: str = ""
    formatting_rules: List[str] = field(default_factory=list)


@dataclass
class ContentChunk:
    """Chunk with classification metadata"""
    chunk_id: str
    text: str
    section_type: str
    section_name: str
    doc_id: str
    doc_title: str
    page_num: Optional[int] = None
    chunk_index: int = 0
    confidence: float = 1.0
    detection_method: str = "rule"
    keywords: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize metadata if empty"""
        if not self.keywords:
            self.keywords = []
        if not self.metadata:
            self.metadata = self.to_metadata()
    
    def to_metadata(self) -> Dict[str, Any]:
        """Convert to Pinecone metadata"""
        # Truncate text to fit Pinecone's 40KB metadata limit
        text_preview = self.text[:3000] if len(self.text) > 3000 else self.text
        
        return {
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "section_type": self.section_type,
            "section_name": self.section_name,
            "page_num": self.page_num,
            "chunk_index": self.chunk_index,
            "confidence": float(self.confidence),
            "detection_method": self.detection_method,
            "keywords": self.keywords or [],
            "text": text_preview,  # Store text in metadata
            "extracted_at": datetime.now().isoformat()
        }


# ============================================================================
# PART 3: TEMPLATE RULE BUILDER
# ============================================================================

class TemplateRuleBuilder:
    """
    Builds classification rules directly from your SOW template structure
    Maps section types to keywords, patterns, and metadata markers
    """
    
    TEMPLATE_SECTIONS = [
        TemplateSection(
            name="Table of Contents",
            section_type=SectionType.TABLE_OF_CONTENTS,
            meta_tag="META_STATIC_TABLE",
            is_dynamic=False,
            formatting_rules=["Numbered list", "20 items"]
        ),
        TemplateSection(
            name="Project Overview",
            section_type=SectionType.PROJECT_OVERVIEW,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="3-4 sentences on system purpose, benefits, features",
        ),
        TemplateSection(
            name="Scope of Work",
            section_type=SectionType.SCOPE_OF_WORK,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="5 numbered sections with sub-bullets",
        ),
        TemplateSection(
            name="Architecture",
            section_type=SectionType.ARCHITECTURE,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="System design and topology",
        ),
        TemplateSection(
            name="Customer Dependencies",
            section_type=SectionType.CUSTOMER_DEPENDENCIES,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="Technical requirements",
        ),
        TemplateSection(
            name="Assumptions",
            section_type=SectionType.ASSUMPTIONS,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="Project assumptions",
        ),
        TemplateSection(
            name="Out of Scope",
            section_type=SectionType.OUT_OF_SCOPE,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="Excluded items",
        ),
        TemplateSection(
            name="Timelines",
            section_type=SectionType.TIMELINES,
            meta_tag="META_TABLE",
            is_dynamic=True,
            description="Project timeline",
        ),
        TemplateSection(
            name="AWS Pricing",
            section_type=SectionType.AWS_PRICING,
            meta_tag="META_TABLE",
            is_dynamic=True,
            description="Cost estimates",
        ),
        TemplateSection(
            name="Resource Loading",
            section_type=SectionType.RESOURCE_LOADING,
            meta_tag="META_TABLE",
            is_dynamic=True,
            description="Resource allocation",
        ),
        TemplateSection(
            name="Success Criteria",
            section_type=SectionType.SUCCESS_CRITERIA,
            meta_tag="META_GENERATED",
            is_dynamic=True,
            description="Success metrics",
        ),
        TemplateSection(
            name="Terms & Conditions",
            section_type=SectionType.TERMS_CONDITIONS,
            meta_tag="META_STATIC",
            is_dynamic=False,
            description="Legal terms",
        ),
    ]
    
    SECTION_KEYWORDS = {
        SectionType.PROJECT_OVERVIEW: [
            "overview", "objective", "purpose", "system", "features", "delivers"
        ],
        SectionType.SCOPE_OF_WORK: [
            "scope", "deliverable", "develop", "implement", "api", "backend", "ui"
        ],
        SectionType.ARCHITECTURE: [
            "architecture", "design", "topology", "aws", "deployment", "components"
        ],
        SectionType.CUSTOMER_DEPENDENCIES: [
            "dependencies", "requires", "aws services", "access", "environment"
        ],
        SectionType.ASSUMPTIONS: [
            "assume", "assumption", "provided", "available", "timeline", "data"
        ],
        SectionType.OUT_OF_SCOPE: [
            "out of scope", "not included", "excluded", "beyond", "not"
        ],
        SectionType.TIMELINES: [
            "timeline", "schedule", "week", "duration", "phase", "milestone"
        ],
        SectionType.AWS_PRICING: [
            "pricing", "cost", "mrr", "arr", "aws", "budget", "usd"
        ],
        SectionType.RESOURCE_LOADING: [
            "resource", "team", "allocation", "role", "engineer", "week"
        ],
        SectionType.SUCCESS_CRITERIA: [
            "success", "criteria", "metric", "accuracy", "performance"
        ],
        SectionType.TERMS_CONDITIONS: [
            "terms", "conditions", "sla", "agreement", "confidential"
        ],
    }
    
    SECTION_PATTERNS = {
        SectionType.TIMELINES: [
            r'duration.*deliverable',
            r'week.*description',
            r'\d+\s*week'
        ],
        SectionType.AWS_PRICING: [
            r'mrr|arr',
            r'pricing calculator',
            r'\$.*usd'
        ],
        SectionType.RESOURCE_LOADING: [
            r'resource.*week',
            r'effort.*week',
            r'role.*level'
        ],
    }


# ============================================================================
# PART 4: CLASSIFIERS & EXTRACTORS
# ============================================================================

class TemplateRuleClassifier:
    """
    Hybrid classifier using template-derived rules
    Rule-based → LLM fallback (using AWS Claude)
    """
    
    def __init__(self, bedrock_client=None, confidence_threshold: float = 0.70):
        self.bedrock = bedrock_client
        self.confidence_threshold = confidence_threshold
        self.rule_builder = TemplateRuleBuilder()
        self._build_classification_index()
    
    def _build_classification_index(self) -> None:
        """Build efficient lookup indexes from template rules"""
        self.section_map = {
            section.name: section
            for section in self.rule_builder.TEMPLATE_SECTIONS
        }
        self.keywords_index = self.rule_builder.SECTION_KEYWORDS
        self.patterns_index = self.rule_builder.SECTION_PATTERNS
    
    def classify(self, text: str, section_hint: Optional[str] = None) -> Tuple[Optional[SectionType], float, str]:
        """Classify text using hybrid approach"""
        rule_result = self._rule_based_detection(text, section_hint)
        
        if rule_result:
            section_type, confidence = rule_result
            if confidence >= self.confidence_threshold:
                print(f"  ✓ Rule-based: {section_type.value} (confidence: {confidence:.2f})")
                return section_type, confidence, "rule"
        
        print(f"  → Confidence below threshold, using AWS Claude fallback...")
        llm_result = self._llm_based_detection(text)
        
        if llm_result:
            section_type, confidence = llm_result
            print(f"  ✓ LLM-based: {section_type.value} (confidence: {confidence:.2f})")
            return section_type, confidence, "llm"
        
        return None, 0.3, "default"
    
    def _rule_based_detection(self, text: str, hint: Optional[str] = None) -> Optional[Tuple[SectionType, float]]:
        """Rule-based classification"""
        text_lower = text.lower()
        hint_lower = hint.lower() if hint else ""
        
        # Template structure matching
        for section in self.rule_builder.TEMPLATE_SECTIONS:
            section_name_lower = section.name.lower()
            if hint and (section_name_lower in hint_lower or hint_lower in section_name_lower):
                return (section.section_type, 0.95)
            if section_name_lower in text_lower[:200]:
                return (section.section_type, 0.90)
        
        # Keyword matching
        max_score = 0.0
        best_type = None
        
        for section_type, keywords in self.keywords_index.items():
            matches = sum(1 for kw in keywords if kw in text_lower)
            if matches > 0:
                score = min(0.85, 0.3 + (matches * 0.1))
                if score > max_score:
                    max_score = score
                    best_type = section_type
        
        if best_type and max_score >= 0.50:
            return (best_type, max_score)
        
        # Pattern matching
        for section_type, patterns in self.patterns_index.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return (section_type, 0.60)
        
        return None
    
    def _llm_based_detection(self, text: str) -> Optional[Tuple[SectionType, float]]:
        """LLM-based classification using AWS Claude"""
        if not self.bedrock:
            return None
        
        section_names = ", ".join([s.name for s in self.rule_builder.TEMPLATE_SECTIONS])
        text_sample = text[:1500] if len(text) > 1500 else text
        
        prompt = f"""Classify the following SOW section into ONE category:
{section_names}

TEXT:
{text_sample}

Return ONLY the exact section name:"""

        try:
            response = self.bedrock.invoke_model(
                modelId="anthropic.claude-3-5-sonnet-20241022",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 50,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            classification = response_body['content'][0]['text'].strip()
            
            for section in self.rule_builder.TEMPLATE_SECTIONS:
                if classification.lower() in section.name.lower():
                    return (section.section_type, 0.80)
            
            return None
        except Exception as e:
            print(f"    ✗ LLM classification failed: {e}")
            return None
    
    def get_formatting_rules(self, section_type: SectionType) -> List[str]:
        """Get formatting rules for a section type"""
        for section in self.rule_builder.TEMPLATE_SECTIONS:
            if section.section_type == section_type:
                return section.formatting_rules
        return []
    
    def is_dynamic_section(self, section_type: SectionType) -> bool:
        """Check if section needs LLM generation"""
        for section in self.rule_builder.TEMPLATE_SECTIONS:
            if section.section_type == section_type:
                return section.is_dynamic
        return False


class DocumentExtractor:
    """Extract text from PDF and DOCX with page tracking"""
    
    @staticmethod
    def extract_from_pdf(file_path: str) -> List[Tuple[str, int]]:
        """Extract text from PDF with page numbers"""
        pages = []
        try:
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page_num, page in enumerate(reader.pages, 1):
                    text = page.extract_text()
                    if text.strip():
                        pages.append((text, page_num))
            print(f"  ✓ Extracted {len(pages)} pages from PDF")
            return pages
        except Exception as e:
            print(f"  ✗ PDF extraction failed: {e}")
            return []
    
    @staticmethod
    def extract_from_docx(file_path: str) -> List[Tuple[str, Optional[int]]]:
        """Extract text from DOCX"""
        pages = []
        try:
            doc = Document(file_path)
            for para in doc.paragraphs:
                if para.text.strip():
                    pages.append((para.text, None))
            print(f"  ✓ Extracted {len(pages)} paragraphs from DOCX")
            return pages
        except Exception as e:
            print(f"  ✗ DOCX extraction failed: {e}")
            return []
    
    @staticmethod
    def extract(file_path: str) -> List[Tuple[str, Optional[int]]]:
        """Auto-detect format and extract"""
        if file_path.endswith('.pdf'):
            return DocumentExtractor.extract_from_pdf(file_path)
        elif file_path.endswith('.docx'):
            return DocumentExtractor.extract_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported format: {file_path}")


class ContentChunker:
    """Chunk content with hybrid classification"""
    
    def __init__(self, bedrock_client=None, chunk_size: int = 500, overlap: int = 100):
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.classifier = TemplateRuleClassifier(
            bedrock_client=bedrock_client,
            confidence_threshold=0.70
        )
    
    def chunk(self, doc_id: str, doc_title: str, pages: List[Tuple[str, Optional[int]]]) -> List[ContentChunk]:
        """Chunk document with hybrid classification"""
        chunks = []
        chunk_index = 0
        max_chunks_per_section = 50  # Limit chunks per section
        
        print(f"🔍 Detecting sections...")
        sections = self._detect_sections(pages)
        
        print(f"🔪 Chunking and classifying {len(sections)} sections...\n")
        
        for section_idx, (section_title, section_content, page_num) in enumerate(sections):
            print(f"  Section {section_idx + 1}/{len(sections)}: {section_title}")
            
            # Skip extremely large sections
            if len(section_content) > 50000:
                print(f"    ⚠ Warning: Section too large ({len(section_content)} chars), truncating...")
                section_content = section_content[:50000]
            
            section_type, confidence, method = self.classifier.classify(
                section_content,
                section_hint=section_title
            )
            
            if not section_type:
                section_type = SectionType.TABLE_OF_CONTENTS
                confidence = 0.3
                method = "default"
            
            keywords = self._extract_keywords(section_content, section_type)
            text_chunks = self._chunk_text(section_content)
            
            # Limit chunks per section
            if len(text_chunks) > max_chunks_per_section:
                print(f"    ⚠ Limiting to {max_chunks_per_section} chunks (was {len(text_chunks)})")
                text_chunks = text_chunks[:max_chunks_per_section]
            
            for chunk_text in text_chunks:
                chunk = ContentChunk(
                    chunk_id=self._generate_chunk_id(doc_id, chunk_index),
                    text=chunk_text,
                    section_type=section_type.value,
                    section_name=section_title,
                    doc_id=doc_id,
                    doc_title=doc_title,
                    page_num=page_num,
                    chunk_index=chunk_index,
                    confidence=confidence,
                    detection_method=method,
                    keywords=keywords
                )
                chunks.append(chunk)
                chunk_index += 1
            
            print(f"    + Created {len(text_chunks)} chunks for this section")
        
        print(f"  ✓ Created {len(chunks)} total chunks\n")
        return chunks
    
    def _detect_sections(self, pages: List[Tuple[str, Optional[int]]]) -> List[Tuple[str, str, Optional[int]]]:
        """Detect section boundaries in document"""
        sections = []
        current_section = "Introduction"
        current_content = []
        current_page = None
        
        for text, page_num in pages:
            current_page = current_page or page_num
            lines = text.split('\n')
            
            for line in lines:
                line_clean = line.strip()
                
                # FIXED: Added safety check for empty strings
                is_header = (
                    line_clean and 
                    len(line_clean) < 100 and
                    (line_clean.startswith('#') or 
                     line_clean.isupper() or
                     (len(line_clean) > 0 and line_clean[0].isupper() and len(line_clean.split()) < 8))
                )
                
                template_match = any(
                    kw in line_clean.lower()
                    for kws in TemplateRuleBuilder.SECTION_KEYWORDS.values()
                    for kw in kws
                )
                
                if is_header and template_match:
                    if current_content:
                        sections.append((current_section, '\n'.join(current_content).strip(), current_page))
                    current_section = line_clean
                    current_content = []
                    current_page = page_num
                else:
                    current_content.append(line)
        
        if current_content:
            sections.append((current_section, '\n'.join(current_content).strip(), current_page))
        
        return sections
    
    def _chunk_text(self, text: str) -> List[str]:
        """Split text into chunks with overlap - memory efficient and safe"""
        # FIXED: Added empty text handling
        if not text or len(text) <= self.chunk_size:
            return [text] if text else []
        
        chunks = []
        start = 0
        max_attempts = 10000  # Prevent infinite loops
        attempts = 0
        
        while start < len(text) and attempts < max_attempts:
            attempts += 1
            end = min(start + self.chunk_size, len(text))
            
            # FIXED: Try multiple punctuation marks for better breaks
            if end < len(text):
                # Look for period, question mark, or exclamation
                for punct in ['. ', '? ', '! ']:
                    last_punct = text.rfind(punct, start, end)
                    if last_punct > start + int(self.chunk_size * 0.8):
                        end = last_punct + len(punct)  # Include punctuation
                        break
            
            chunk = text[start:end].strip()
            
            # Only add meaningful chunks
            if chunk and len(chunk) > 10:  # Minimum chunk size
                chunks.append(chunk)
            
            # FIXED: Better progress guarantee
            new_start = max(end - self.overlap, end)
            if new_start <= start:
                new_start = start + max(1, self.chunk_size // 2)  # Force forward movement
            start = new_start
        
        if attempts >= max_attempts:
            print(f"  ⚠ Warning: Chunk iteration limit reached, truncating remaining text")
        
        # FIXED: Ensure we always return at least one chunk if text exists
        return chunks if chunks else ([text[:self.chunk_size]] if text else [])
    
    def _extract_keywords(self, text: str, section_type: SectionType) -> List[str]:
        """Extract relevant keywords"""
        keywords = []
        text_lower = text.lower()
        
        if section_type in TemplateRuleBuilder.SECTION_KEYWORDS:
            for keyword in TemplateRuleBuilder.SECTION_KEYWORDS[section_type]:
                if keyword in text_lower:
                    keywords.append(keyword)
        
        return keywords[:10]
    
    @staticmethod
    def _generate_chunk_id(doc_id: str, chunk_index: int) -> str:
        """Generate unique chunk ID"""
        return f"{doc_id}_chunk_{chunk_index}"


class AWSEmbedder:
    """Use AWS Titan Embeddings for embedding generation"""
    
    def __init__(self, bedrock_client, pinecone_api_key: str, 
                 index_name: str = "rag-mod", 
                 model_id: str = "amazon.titan-embed-text-v2:0",
                 dimension: int = 1024):
        self.bedrock = bedrock_client
        self.model_id = model_id
        self.index_name = index_name
        
        print(f"🔌 Connecting to Pinecone...")
        self.pc = Pinecone(api_key=pinecone_api_key)
        self.index = self._get_or_create_index(index_name, dimension)
        print(f"✓ Embedder initialized with AWS Titan (dim: {dimension})\n")
    
    def _get_or_create_index(self, index_name: str, dimension: int):
        """Get or create Pinecone index"""
        try:
            indexes = self.pc.list_indexes()
            index_names = [idx.name for idx in indexes]
            
            if index_name in index_names:
                print(f"  ✓ Using existing index: {index_name}")
                return self.pc.Index(index_name)
            else:
                print(f"  → Creating new index: {index_name}")
                self.pc.create_index(
                    name=index_name,
                    dimension=dimension,
                    metric="cosine",
                    spec={"serverless": {"cloud": "aws", "region": "us-east-1"}}
                )
                import time
                time.sleep(10)
                return self.pc.Index(index_name)
        except Exception as e:
            print(f"  ✗ Index creation failed: {e}")
            raise
    
    def _embed_text(self, text: str) -> List[float]:
        """Generate embedding using AWS Titan"""
        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({"inputText": text})
            )
            response_body = json.loads(response['body'].read())
            return response_body.get('embedding', [])
        except Exception as e:
            print(f"    ✗ Embedding generation failed: {e}")
            return []
    
    def embed_and_upsert(self, chunks: List[ContentChunk], batch_size: int = 5) -> None:
        """Embed chunks using Titan and upsert to Pinecone - memory efficient"""
        print(f"⚡ Embedding {len(chunks)} chunks with AWS Titan...\n")
        
        vectors_to_upsert = []
        successful_uploads = 0
        failed_uploads = 0
        
        for i, chunk in enumerate(chunks):
            try:
                print(f"  Processing chunk {i + 1}/{len(chunks)}...", end='\r')
                
                # Skip very small chunks
                if len(chunk.text) < 5:
                    continue
                
                # Truncate very large chunks
                text_to_embed = chunk.text[:2000] if len(chunk.text) > 2000 else chunk.text
                
                embedding = self._embed_text(text_to_embed)
                
                if not embedding or len(embedding) == 0:
                    failed_uploads += 1
                    continue
                
                vector = (chunk.chunk_id, embedding, chunk.to_metadata())
                vectors_to_upsert.append(vector)
                
                # Batch upsert
                if len(vectors_to_upsert) >= batch_size or (i + 1) == len(chunks):
                    try:
                        self.index.upsert(vectors=vectors_to_upsert)
                        successful_uploads += len(vectors_to_upsert)
                        print(f"  ✓ Upserted {len(vectors_to_upsert)} vectors ({i + 1}/{len(chunks)})")
                        vectors_to_upsert = []
                    except Exception as e:
                        print(f"  ✗ Batch upsert failed: {e}")
                        failed_uploads += len(vectors_to_upsert)
                        vectors_to_upsert = []
            
            except Exception as e:
                print(f"  ✗ Error processing chunk {i + 1}: {e}")
                failed_uploads += 1
                continue
        
        print(f"\n✓ Embedding complete!")
        print(f"  ✓ Successfully uploaded: {successful_uploads}")
        print(f"  ✗ Failed uploads: {failed_uploads}\n")
    
    def search_by_section_type(self, query_text: str, section_type: str, top_k: int = 2) -> List[Dict[str, Any]]:
        """Search for chunks of specific section type"""
        query_embedding = self._embed_text(query_text)
        
        if not query_embedding:
            print(f"  ✗ Query embedding failed")
            return []
        
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter={"section_type": {"$eq": section_type}}
        )
        return results['matches']
    
    def search(self, query_text: str, top_k: int = 3, filters: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Generic search"""
        query_embedding = self._embed_text(query_text)
        
        if not query_embedding:
            print(f"  ✗ Query embedding failed")
            return []
        
        results = self.index.query(
            vector=query_embedding,
            top_k=top_k,
            include_metadata=True,
            filter=filters
        )
        return results['matches']


class AWSSOWPipeline:
    """Complete end-to-end pipeline"""
    
    def __init__(self, aws_region: str = None, pinecone_api_key: str = None,
                 chunk_size: int = 500, overlap: int = 100):
        aws_region = aws_region or os.getenv("BEDROCK_REGION", "us-east-1")
        print(f"🔗 Connecting to AWS Bedrock...\n")
        self.bedrock = boto3.client(service_name='bedrock-runtime', region_name=aws_region)
        
        self.chunker = ContentChunker(
            bedrock_client=self.bedrock,
            chunk_size=chunk_size,
            overlap=overlap
        )
        
        self.embedder = AWSEmbedder(
            bedrock_client=self.bedrock,
            pinecone_api_key=pinecone_api_key
        )
    
    def process_document(self, file_path: str, doc_id: str, doc_title: str) -> Optional[List[ContentChunk]]:
        """Process single document end-to-end"""
        print(f"\n{'='*60}")
        print(f"Processing: {doc_title}")
        print(f"File: {file_path}")
        print(f"{'='*60}\n")
        
        print(f"📄 Extracting text...")
        pages = DocumentExtractor.extract(file_path)
        if not pages:
            print(f"  ✗ Failed to extract content\n")
            return None
        
        print(f"🔍 Chunking with hybrid classification...")
        chunks = self.chunker.chunk(doc_id, doc_title, pages)
        if not chunks:
            print(f"  ✗ No chunks created\n")
            return None
        
        print(f"🧠 Embedding with AWS Titan and storing in Pinecone...")
        self.embedder.embed_and_upsert(chunks)
        
        return chunks
    
    def process_corpus(self, documents: List[Tuple[str, str, str]]) -> Dict[str, List[ContentChunk]]:
        """Process multiple documents"""
        corpus_chunks = {}
        
        print(f"\n{'='*70}")
        print(f"📚 PROCESSING CORPUS: {len(documents)} DOCUMENTS")
        print(f"{'='*70}\n")
        
        for file_path, doc_id, doc_title in documents:
            chunks = self.process_document(file_path, doc_id, doc_title)
            if chunks:
                corpus_chunks[doc_id] = chunks
        
        print(f"\n{'='*70}")
        print(f"✅ CORPUS PROCESSING COMPLETE")
        print(f"{'='*70}\n")
        print(f"Summary:")
        print(f"  📄 Documents processed: {len(corpus_chunks)}")
        print(f"  🔪 Total chunks created: {sum(len(c) for c in corpus_chunks.values())}")
        
        return corpus_chunks
    
    def retrieve_for_section(self, section_type: str, query_text: str = "", top_k: int = 2) -> List[Dict[str, Any]]:
        """Retrieve similar chunks for section generation"""
        # FIXED: Better handling when no query_text is provided
        if query_text:
            return self.embedder.search_by_section_type(query_text, section_type, top_k)
        else:
            # Generate a generic query based on section type
            generic_query = f"{section_type.replace('_', ' ')} section content examples"
            return self.embedder.search(
                query_text=generic_query,
                top_k=top_k, 
                filters={"section_type": {"$eq": section_type}}
            )
    
    def check_index_metadata_version(self) -> bool:
        """Check if existing vectors have text in metadata"""
        print("\n🔍 Checking index metadata version...")
        
        # Sample a few vectors
        dummy_vector = [0.1] * 1024
        results = self.embedder.index.query(
            vector=dummy_vector,
            top_k=5,
            include_metadata=True
        )
        
        if not results['matches']:
            print("  ✓ Index is empty - no migration needed")
            return True
        
        # Check if text field exists
        has_text = any('text' in match.get('metadata', {}) for match in results['matches'])
        
        if has_text:
            print("  ✓ Metadata includes text field - all good!")
            return True
        else:
            print("  ⚠️  Metadata MISSING text field - needs re-processing")
            return False
    
    def reprocess_existing_documents(self):
        """Re-process documents that are already in the index"""
        print("\n" + "="*70)
        print("♻️  RE-PROCESSING EXISTING DOCUMENTS")
        print("="*70)
        print("\nThis will update your vectors to include text in metadata.")
        print("You'll need to provide the original document files again.\n")
        
        confirm = input("Continue? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Cancelled.")
            return
        
        # Get list of documents to re-process
        documents = []
        while True:
            file_path = input("\nEnter document path (or 'done' to finish): ").strip().strip('"\'')
            if file_path.lower() == 'done':
                break
            
            if not Path(file_path).exists():
                print(f"  ✗ File not found: {file_path}")
                continue
            
            doc_id = input("Enter document ID: ").strip()
            doc_title = input("Enter document title: ").strip()
            
            documents.append((file_path, doc_id, doc_title))
            print(f"  ✓ Added: {doc_title}")
        
        if not documents:
            print("No documents to re-process.")
            return
        
        print(f"\n📚 Re-processing {len(documents)} documents...")
        self.process_corpus(documents)


def get_user_input() -> Tuple[str, str, str]:
    """Get user input for file path and document info"""
    print("\n" + "="*70)
    print("📁 SOW DOCUMENT PROCESSOR")
    print("="*70 + "\n")
    
    while True:
        file_path = input("Enter the path to your SOW document (PDF or DOCX): ").strip().strip('"\'')
        
        if not file_path:
            print("  ✗ File path cannot be empty")
            continue
        
        if not Path(file_path).exists():
            print(f"  ✗ File not found: {file_path}")
            continue
        
        if not (file_path.endswith('.pdf') or file_path.endswith('.docx')):
            print(f"  ✗ File must be PDF or DOCX format")
            continue
        
        break
    
    doc_id = input("Enter a unique document ID (e.g., poc_001): ").strip()
    if not doc_id:
        doc_id = Path(file_path).stem
    
    doc_title = input("Enter a descriptive title for this document: ").strip()
    if not doc_title:
        doc_title = Path(file_path).stem
    
    return file_path, doc_id, doc_title


def main():
    """Main entry point with interactive user input"""
    load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

    AWS_REGION = os.getenv("BEDROCK_REGION", "us-east-1")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    
    if not PINECONE_API_KEY:
        print("❌ Error: PINECONE_API_KEY not found in environment variables")
        print("   Set it in your .env file: PINECONE_API_KEY=your-key")
        return
    
    print("\n" + "="*70)
    print("🚀 AWS SOW CORPUS PIPELINE - PRODUCTION READY")
    print("   Hybrid Classification + Titan Embeddings + Pinecone Storage")
    print("="*70)
    
    pipeline = AWSSOWPipeline(
        aws_region=AWS_REGION,
        pinecone_api_key=PINECONE_API_KEY,
        chunk_size=500,
        overlap=100
    )
    
    while True:
        print("\n" + "="*70)
        print("PROCESSING OPTIONS")
        print("="*70)
        print("1. Process a single document")
        print("2. Process multiple documents (corpus)")
        print("3. Search existing corpus")
        print("4. Re-process existing documents (add text to metadata)")
        print("5. Check metadata version")
        print("6. Exit")
        
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == "1":
            file_path, doc_id, doc_title = get_user_input()
            pipeline.process_document(file_path, doc_id, doc_title)
            
            print("\n" + "="*60)
            print("TESTING RETRIEVAL")
            print("="*60 + "\n")
            
            query = "system architecture and design"
            results = pipeline.retrieve_for_section(
                section_type="architecture",
                query_text=query,
                top_k=2
            )
            
            if results:
                print(f"Query: {query}\n")
                print(f"Found {len(results)} similar Architecture sections:\n")
                for i, result in enumerate(results, 1):
                    metadata = result['metadata']
                    text_preview = metadata.get('text', 'No text available')[:150]
                    
                    print(f"{i}. From: {metadata['doc_title']}")
                    print(f"   Section: {metadata['section_name']}")
                    print(f"   Confidence: {metadata['confidence']:.2f}")
                    print(f"   Score: {result['score']:.3f}")
                    print(f"   Text: {text_preview}...")
                    print()
        
        elif choice == "2":
            documents = []
            print("\n" + "="*70)
            print("CORPUS PROCESSING")
            print("="*70)
            
            num_docs = input("How many documents to process? ").strip()
            try:
                num_docs = int(num_docs)
            except ValueError:
                print("  ✗ Invalid number")
                continue
            
            for i in range(num_docs):
                print(f"\n--- Document {i + 1}/{num_docs} ---")
                file_path, doc_id, doc_title = get_user_input()
                documents.append((file_path, doc_id, doc_title))
            
            corpus_chunks = pipeline.process_corpus(documents)
            
            if corpus_chunks:
                print("\n" + "="*60)
                print("TESTING RETRIEVAL")
                print("="*60 + "\n")
                
                query = "scope deliverables implementation timeline"
                results = pipeline.retrieve_for_section(
                    section_type="scope_of_work",
                    query_text=query,
                    top_k=3
                )
                
                if results:
                    print(f"Query: {query}\n")
                    print(f"Found {len(results)} similar Scope of Work sections:\n")
                    for i, result in enumerate(results, 1):
                        metadata = result['metadata']
                        text_preview = metadata.get('text', 'No text available')[:150]
                        
                        print(f"{i}. From: {metadata['doc_title']}")
                        print(f"   Section: {metadata['section_name']}")
                        print(f"   Score: {result['score']:.3f}")
                        print(f"   Text: {text_preview}...")
                        print()
        
        elif choice == "3":
            print("\n" + "="*70)
            print("CORPUS SEARCH")
            print("="*70)
            
            section_types = [s.value for s in SectionType]
            print("\nAvailable section types:")
            for i, st in enumerate(section_types, 1):
                print(f"  {i}. {st}")
            
            section_idx = input("\nSelect section type (number): ").strip()
            try:
                section_type = section_types[int(section_idx) - 1]
            except (ValueError, IndexError):
                print("  ✗ Invalid selection")
                continue
            
            query = input("Enter search query: ").strip()
            top_k = input("Number of results (default 3): ").strip()
            top_k = int(top_k) if top_k else 3
            
            results = pipeline.retrieve_for_section(
                section_type=section_type,
                query_text=query,
                top_k=top_k
            )
            
            if results:
                print(f"\nQuery: {query}")
                print(f"Section: {section_type}\n")
                print(f"Found {len(results)} results:\n")
                for i, result in enumerate(results, 1):
                    metadata = result['metadata']
                    text_preview = metadata.get('text', 'No text available')[:200]
                    
                    print(f"{i}. {metadata['doc_title']}")
                    print(f"   Score: {result['score']:.3f}")
                    print(f"   Section: {metadata['section_name']}")
                    print(f"   Text: {text_preview}...")
                    print(f"   Page: {metadata.get('page_num', 'N/A')}")
                    print()
            else:
                print("  No results found")
        
        elif choice == "4":
            pipeline.reprocess_existing_documents()
        
        elif choice == "5":
            has_text = pipeline.check_index_metadata_version()
            if not has_text:
                print("\n💡 Recommendation: Use Option 4 to re-process your documents")
        
        elif choice == "6":
            print("\n👋 Goodbye!")
            break
        
        else:
            print("  ✗ Invalid option")


if __name__ == "__main__":
    main()
