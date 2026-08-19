"""
Configuration for POC Generator (LangGraph Version)
✅ UPDATED: Static ShellKode Details + Dynamic Client Company
"""
import os
from pathlib import Path
from botocore.config import Config as BotocoreConfig


class Config:
    """Configuration class for POC generator with static ShellKode details"""
    
    def __init__(self):
        # =====================================================================
        # BASE DIRECTORIES
        # =====================================================================
        self.BASE_DIR = Path(__file__).resolve().parents[2]  # backend/
        self.TEMPLATES_DIR = self.BASE_DIR / "templates"
        self.ASSETS_DIR = self.BASE_DIR / "assets"
        self.OUTPUT_DIR = self.BASE_DIR / "output"  # Will be overridden with temp dirs

        # Create only essential directories (not output dir for cloud-only mode)
        self.TEMPLATES_DIR.mkdir(exist_ok=True)
        self.ASSETS_DIR.mkdir(exist_ok=True)
        # Note: OUTPUT_DIR not created - using temporary directories for cloud-only mode
        
        # =====================================================================
        # ✅ STATIC SHELLKODE ORGANIZATION DETAILS (NO WEB SCRAPING)
        # =====================================================================
        
        self.AUTHOR_ORG = "ShellKode"
        
        self.AUTHOR_ORG_SHORT = "ShellKode"
        
        self.AUTHOR_ORG_DESCRIPTION = (
            "ShellKode specializes in developing advanced data and AI solutions for businesses. "
            "The company builds robust data foundations that transform raw inputs into actionable intelligence, "
            "creates self-improving machine learning systems, and offers AI-driven services to modernize "
            "applications and infrastructure for cloud environments. ShellKode's expertise lies in enhancing "
            "data processing, predictive modeling, and cloud migration capabilities."
        )
        
        # =====================================================================
        # AWS BEDROCK CONFIGURATION
        # =====================================================================
        
        self.AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
        # Using Claude Sonnet 4 - latest model with enhanced capabilities  
        self.MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"
        
        # Model parameters
        # Large single responses were the main source of truncated/invalid JSON.
        # The writer now works section-by-section, so these are safe upper bounds
        # rather than a target for every call.
        self.MAX_TOKENS = 8192
        self.SECTION_MAX_TOKENS = 6000
        self.TEMPERATURE = 0.2
        # The preview UI currently stops polling after five minutes. Independent
        # SOW sections share one immutable baseline and can safely be authored in
        # parallel. Keep this configurable for Bedrock account quota tuning.
        try:
            configured_workers = int(os.environ.get("SOW_SECTION_WORKERS", "4"))
        except ValueError:
            configured_workers = 4
        self.SOW_SECTION_WORKERS = max(1, min(configured_workers, 8))
        
        # Boto3 timeout configuration
        self.BOTO_CONFIG = BotocoreConfig(
            read_timeout=9000,
            connect_timeout=30,
            retries={'max_attempts': 3}
        )
        
        # =====================================================================
        # DOCUMENT STYLING - Updated to match brand specifications
        # =====================================================================
        
        # Arial is intentionally used in the Word body for renderer portability.
        # The branded cover continues to use the bundled DM Sans font files.
        self.FONT_FAMILY = "Arial"
        self.FONT_SIZE_COVER_COMPANY = 39  # Cover page company name
        self.FONT_SIZE_COVER_TITLE = 16    # Cover page project title  
        self.FONT_SIZE_COVER_SUBTITLE = 15 # Author organization on cover
        self.FONT_SIZE_COVER_PREPARED = 12 # Prepared by text
        self.FONT_SIZE_TITLE = 26          # Legacy compatibility
        self.FONT_SIZE_HEADING1 = 16       # narrative_proposal preset
        self.FONT_SIZE_HEADING2 = 13       # narrative_proposal preset
        self.FONT_SIZE_BODY = 11           # Body text and tables
        self.FONT_SIZE_FOOTER = 9          # Footer text
        self.LINE_SPACING = 1.333          # narrative_proposal preset
        
        # Brand Colors - Updated to match specifications
        self.COLOR_PRIMARY_HEX = "#7B3FF2"      # Primary Purple
        self.COLOR_PRIMARY = (123, 63, 242)     # Primary Purple RGB
        self.COLOR_LIGHT_PURPLE_HEX = "#C8B6E8" # Light Purple
        self.COLOR_LIGHT_PURPLE = (200, 182, 232) # Light Purple RGB
        self.COLOR_SUBTITLE_HEX = "#666666"     # Subtitle Gray
        self.COLOR_SUBTITLE = (102, 102, 102)   # Subtitle Gray RGB
        self.COLOR_TABLE_HEADER_TEXT = (255, 255, 255) # White text for table headers
        self.COLOR_SECONDARY = (128, 128, 128)  # Gray (legacy)
        self.COLOR_ACCENT = (123, 63, 242)      # Same as primary (legacy)
        
        # =====================================================================
        # PAGE SETTINGS - Updated to match specifications
        # =====================================================================
        
        self.PAGE_SIZE = "LETTER"  # 8.5 x 11 inches; benchmark/business standard
        
        # Cover page margins (full-bleed)
        self.COVER_MARGIN_TOP = 0
        self.COVER_MARGIN_BOTTOM = 0
        self.COVER_MARGIN_LEFT = 0
        self.COVER_MARGIN_RIGHT = 0
        
        # Content page margins (1 inch all around)
        self.MARGIN_TOP = 72     # 1 inch = 72 points
        self.MARGIN_BOTTOM = 72  # 1 inch = 72 points
        self.MARGIN_LEFT = 72    # 1 inch = 72 points
        self.MARGIN_RIGHT = 72   # 1 inch = 72 points
        
        # Spacing settings
        self.HEADING_SPACE_BEFORE = 18  # Increased space before headings
        self.HEADING_SPACE_AFTER = 18   # Increased space after headings
        self.SUBHEADING_SPACE_BEFORE = 12  # Increased space before subheadings
        self.SUBHEADING_SPACE_AFTER = 12   # Increased space after subheadings
        self.PARAGRAPH_SPACE_AFTER = 12    # Increased space after paragraphs
        self.BULLET_SPACE_AFTER = 4        # Reduced space after bullet points
        
        # Bullet list indentation
        self.BULLET_INDENT_LEVEL1 = 20
        self.BULLET_INDENT_LEVEL2 = 30
        self.BULLET_INDENT_LEVEL3 = 50
        
        # Footer settings
        self.FOOTER_POSITION = 0.7  # 0.7 inch from bottom
        
        # =====================================================================
        # TEMPLATE AND ASSET FILES
        # =====================================================================
        
        self.POC_RULES_FILE = self.TEMPLATES_DIR / "poc_rules.json"
        self.POC_TEMPLATE_FILE = self.TEMPLATES_DIR / "poc_template.md"
        self.PRODUCTION_TEMPLATE_FILE = self.TEMPLATES_DIR / "production_template.md"
        self.POC_TO_PROD_TEMPLATE_FILE = self.TEMPLATES_DIR / "poc_to_prod_template.md"
        self.COVER_PAGE_IMAGE = self.ASSETS_DIR / "coverpage.png"
        self.ARCHITECTURE_DIAGRAM = self.ASSETS_DIR / "architecture_diagram.png"
        
        # =====================================================================
        # GOOGLE SEARCH API (Optional - for company info web scraping)
        # =====================================================================
        
        self.GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
        self.GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")
        
        # =====================================================================
        # DYNAMODB CONFIGURATION
        # =====================================================================
        
        self.DYNAMODB_TABLE_RAG_SCHEMA = 'rag-schema'
        self.DYNAMODB_TABLE_POC_DOCUMENTS = 'agentic-poc'
        
        # =====================================================================
        # SCHEMA CLEANER CONFIGURATION
        # =====================================================================
        
        self.SCHEMA_CLEANING_ENABLED = True
        self.SCHEMA_CLEANING_STRATEGY = "remove"  # "remove" or "fill"
        
        # =====================================================================
        # DEFAULT VALUES
        # =====================================================================
        
        self.DEFAULT_TIMEZONE = "IST"
        self.DEFAULT_VERSION = "1.0"
    
    # =========================================================================
    # ✅ STATIC SHELLKODE DETAILS METHODS
    # =========================================================================
    
    def get_static_author_details(self):
        """
        Get ShellKode details (STATIC - no web scraping)
        
        Returns:
            dict: ShellKode organization details
        """
        return {
            "author_org": self.AUTHOR_ORG,
            "author_org_short": self.AUTHOR_ORG_SHORT,
            "author_org_description": self.AUTHOR_ORG_DESCRIPTION,
        }
    
    # =========================================================================
    # PLACEHOLDER VALUES METHODS
    # =========================================================================
    
    @staticmethod
    def get_short_name(full_name: str) -> str:
        """
        Extract short company name by removing common suffixes
        
        Args:
            full_name: Full company name
            
        Returns:
            str: Shortened company name
        """
        if not full_name:
            return ''
        
        suffixes = [
            ' Pvt Ltd', ' Private Limited', ' Pvt. Ltd.', ' Pvt.Ltd.',
            ' Ltd', ' LLC', ' Inc', ' Corporation', 
            ' Corp', ' Limited', ' Co', ' Company'
        ]
        
        short_name = full_name
        for suffix in suffixes:
            if short_name.lower().endswith(suffix.lower()):
                short_name = short_name[:len(short_name) - len(suffix)].strip()
                break
        
        return short_name
    
    def get_placeholder_values(self, metadata: dict, company_description: str = ""):
        """
        ✅ Generate all placeholder values for template
        - ShellKode details are STATIC
        - Company details are DYNAMIC
        
        Args:
            metadata: User-provided metadata
                - company_name: Client company name (DYNAMIC)
                - author_name: Person preparing SOW
                - document_date: Document date
                - version: Version number
                - project_title: Project name
                - start_date: Project start date
                - end_date: Project end date
                - objective: Project objective
            
            company_description: Company description (web-scraped or provided)
            
        Returns:
            dict: All placeholder values for template rendering
        """
        
        # Start with static ShellKode values
        placeholders = self.get_static_author_details()
        
        # Add dynamic values from metadata
        company_name = metadata.get('company_name', 'Client Company')
        company_name_short = self.get_short_name(company_name)
        
        placeholders.update({
            # ✅ DYNAMIC - Client Company
            'COMPANY_NAME': company_name,
            'COMPANY_NAME_SHORT': company_name_short,
            'COMPANY_DESCRIPTION': company_description or metadata.get('company_description', 'Professional organization'),
            
            # ✅ USER PROVIDED
            'PROJECT_TITLE': metadata.get('project_title', 'Project'),
            'AUTHOR_NAME': metadata.get('author_name', 'Author'),
            'DOCUMENT_DATE': metadata.get('document_date', ''),
            'VERSION': metadata.get('version', self.DEFAULT_VERSION),
            'START_DATE': metadata.get('start_date', ''),
            'END_DATE': metadata.get('end_date', ''),
            'OBJECTIVE': metadata.get('objective', ''),
        })
        
        return placeholders
    
    def get_bedrock_config(self):
        """
        Get Bedrock configuration dictionary
        
        Returns:
            dict: Bedrock configuration
        """
        return {
            "region": self.AWS_REGION,
            "model_id": self.MODEL_ID,
            "max_tokens": self.MAX_TOKENS,
            "temperature": self.TEMPERATURE
        }
    
    def get_directory_config(self):
        """
        Get all directory configurations
        
        Returns:
            dict: Directory paths
        """
        return {
            "base_dir": str(self.BASE_DIR),
            "templates_dir": str(self.TEMPLATES_DIR),
            "assets_dir": str(self.ASSETS_DIR),
            "output_dir": str(self.OUTPUT_DIR),
        }
    
    def get_document_config(self):
        """
        Get document styling configuration
        
        Returns:
            dict: Document styling settings
        """
        return {
            "font_family": self.FONT_FAMILY,
            "font_size_cover_company": self.FONT_SIZE_COVER_COMPANY,
            "font_size_cover_title": self.FONT_SIZE_COVER_TITLE,
            "font_size_cover_subtitle": self.FONT_SIZE_COVER_SUBTITLE,
            "font_size_cover_prepared": self.FONT_SIZE_COVER_PREPARED,
            "font_size_title": self.FONT_SIZE_TITLE,  # Legacy compatibility
            "font_size_heading1": self.FONT_SIZE_HEADING1,
            "font_size_heading2": self.FONT_SIZE_HEADING2,  # Legacy compatibility
            "font_size_body": self.FONT_SIZE_BODY,
            "font_size_footer": self.FONT_SIZE_FOOTER,
            "line_spacing": self.LINE_SPACING,
            "color_primary": self.COLOR_PRIMARY,
            "color_primary_hex": self.COLOR_PRIMARY_HEX,
            "color_light_purple": self.COLOR_LIGHT_PURPLE,
            "color_light_purple_hex": self.COLOR_LIGHT_PURPLE_HEX,
            "color_subtitle": self.COLOR_SUBTITLE,
            "color_subtitle_hex": self.COLOR_SUBTITLE_HEX,
            "color_table_header_text": self.COLOR_TABLE_HEADER_TEXT,
            "color_secondary": self.COLOR_SECONDARY,
            "color_accent": self.COLOR_ACCENT,
            "page_size": self.PAGE_SIZE,
            "cover_margins": {
                "top": self.COVER_MARGIN_TOP,
                "bottom": self.COVER_MARGIN_BOTTOM,
                "left": self.COVER_MARGIN_LEFT,
                "right": self.COVER_MARGIN_RIGHT,
            },
            "content_margins": {
                "top": self.MARGIN_TOP,
                "bottom": self.MARGIN_BOTTOM,
                "left": self.MARGIN_LEFT,
                "right": self.MARGIN_RIGHT,
            },
            "spacing": {
                "heading_space_before": self.HEADING_SPACE_BEFORE,
                "heading_space_after": self.HEADING_SPACE_AFTER,
                "subheading_space_before": self.SUBHEADING_SPACE_BEFORE,
                "subheading_space_after": self.SUBHEADING_SPACE_AFTER,
                "paragraph_space_after": self.PARAGRAPH_SPACE_AFTER,
            },
            "bullet_indents": {
                "level1": self.BULLET_INDENT_LEVEL1,
                "level2": self.BULLET_INDENT_LEVEL2,
                "level3": self.BULLET_INDENT_LEVEL3,
            },
            "footer_position": self.FOOTER_POSITION,
        }
    
    def validate_templates(self):
        """
        Validate that all required template files exist
        
        Returns:
            dict: Validation results
        """
        results = {
            "poc_template": self.POC_TEMPLATE_FILE.exists(),
            "production_template": self.PRODUCTION_TEMPLATE_FILE.exists(),
            "poc_to_prod_template": self.POC_TO_PROD_TEMPLATE_FILE.exists(),
            "cover_page_image": self.COVER_PAGE_IMAGE.exists(),
            "architecture_diagram": self.ARCHITECTURE_DIAGRAM.exists(),
        }
        
        return results
    
    def print_config_summary(self):
        """Print configuration summary"""
        print("\n" + "="*70)
        print("POC GENERATOR CONFIGURATION SUMMARY")
        print("="*70)
        
        print(f"\n✓ STATIC SHELLKODE DETAILS (No Web Scraping):")
        print(f"  Organization: {self.AUTHOR_ORG}")
        print(f"  Short Name: {self.AUTHOR_ORG_SHORT}")
        print(f"  Description: {self.AUTHOR_ORG_DESCRIPTION[:100]}...")
        
        print(f"\n✓ AWS Configuration:")
        print(f"  Region: {self.AWS_REGION}")
        print(f"  Model: {self.MODEL_ID}")
        print(f"  Max Tokens: {self.MAX_TOKENS}")
        print(f"  Temperature: {self.TEMPERATURE}")
        
        print(f"\n✓ Directories:")
        print(f"  Base: {self.BASE_DIR}")
        print(f"  Templates: {self.TEMPLATES_DIR}")
        print(f"  Output: {self.OUTPUT_DIR}")
        
        print(f"\n✓ Document Styling:")
        print(f"  Font: {self.FONT_FAMILY}")
        print(f"  Page Size: {self.PAGE_SIZE}")
        print(f"  Colors: Primary={self.COLOR_PRIMARY}, Accent={self.COLOR_ACCENT}")
        
        print(f"\n✓ Schema Cleaning:")
        print(f"  Enabled: {self.SCHEMA_CLEANING_ENABLED}")
        print(f"  Strategy: {self.SCHEMA_CLEANING_STRATEGY}")
        
        print(f"\n✓ DynamoDB Tables:")
        print(f"  RAG Schema: {self.DYNAMODB_TABLE_RAG_SCHEMA}")
        print(f"  POC Documents: {self.DYNAMODB_TABLE_POC_DOCUMENTS}")
        
        print("\n" + "="*70)


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

# Create a single config instance for the entire application
config = Config()


if __name__ == "__main__":
    # Print configuration summary when run directly
    config.print_config_summary()
    
    # Validate templates
    print("\n✓ Template Validation:")
    validation = config.validate_templates()
    for template, exists in validation.items():
        status = "✓" if exists else "✗"
        print(f"  {status} {template}: {exists}")
