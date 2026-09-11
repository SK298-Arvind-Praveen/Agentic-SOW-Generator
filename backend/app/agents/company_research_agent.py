"""
Company Research Agent - Simplified without prompt caching
"""
import boto3
from typing import List

from app.core.bedrock_llm import BedrockLLM

# Static Shellkode description
SHELLKODE_DESCRIPTION = "Shellkode specializes in developing advanced data and AI solutions for businesses. The company builds robust data foundations that transform raw inputs into actionable intelligence, creates self-improving machine learning systems, and offers AI-driven services to modernize applications and infrastructure for cloud environments. Shellkode's expertise lies in enhancing data processing, predictive modeling, and cloud migration capabilities."


class CompanyResearchAgent:
    """Simplified company research agent without prompt caching"""
    
    def __init__(self, config):
        self.config = config
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=config.BEDROCK_REGION
        )
        self.llm = BedrockLLM(config, self.bedrock_client)
        
        # In-memory cache for companies researched in this session
        self.session_company_cache = {}
    
    def research_multiple_companies(self, companies: List[str]) -> dict:
        """
        Research multiple companies
        
        Args:
            companies: List of company names to research
            
        Returns:
            Dict of {company_name: description}
        """
        results = {}
        
        print("\n📋 Researching companies...")
        print("="*60)
        
        for idx, company in enumerate(companies, 1):
            if company:
                # Check in-memory session cache first
                if company in self.session_company_cache:
                    results[company] = self.session_company_cache[company]
                    print(f"{idx}. ✅ {company} (from cache)")
                    
                elif company.lower() == "shellkode":
                    results[company] = SHELLKODE_DESCRIPTION
                    self.session_company_cache[company] = SHELLKODE_DESCRIPTION
                    print(f"{idx}. ✅ {company} (static)")
                    
                else:
                    # Research company
                    try:
                        description = self._research_company(company)
                        results[company] = description
                        self.session_company_cache[company] = description
                        print(f"{idx}. ✅ {company} (researched)")
                    except Exception as e:
                        print(f"{idx}. ❌ {company} (error: {e})")
                        results[company] = f"Error researching {company}"
        
        print("="*60)
        return results
    
    def _research_company(self, company_name: str) -> str:
        """
        Research a company using Bedrock
        
        Args:
            company_name: Company to research
            
        Returns:
            Company description
        """
        prompt = f"""Write exactly two brief factual company-profile paragraphs about {company_name}.

Use only widely established facts you are confident apply to this exact organization. Do not
invent size, products, locations, rankings, market position, customers, regulations, or strategic
priorities. Paragraph one should cover its identity, industry, and established products or services.
Paragraph two should cover its established operating model, customer channels, markets, or technology
landscape only where confidently known. Never mention an engagement, Statement of Work, project,
scope, objectives, requirements, problem, proposed solution, or ShellKode. Do not comment on missing
information. Professional tone, concise prose, no heading or bullets. Return only the two paragraphs."""
        
        try:
            result = self.llm.generate(
                prompt,
                task="fast",
                max_tokens=256,
                temperature=0.3,
                call_name=f"Company Context: {company_name}",
                fallback_model_id=getattr(self.config, "ANALYSIS_MODEL_ID", None),
            )
            return result.text.strip()
        except Exception as e:
            print(f"Error researching {company_name}: {e}")
            return ""


# Usage example
if __name__ == "__main__":
    from app.core.config import Config
    
    config = Config()
    agent = CompanyResearchAgent(config)
    
    # Research multiple companies
    companies_to_research = ["Acme Corp", "Tech Solutions", "Shellkode", "DataFlow Inc"]
    print("\n🚀 Researching companies...")
    
    results = agent.research_multiple_companies(companies_to_research)
    
    print("\n" + "="*60)
    print("📊 All results:")
    print("="*60)
    for company, description in results.items():
        print(f"\n{company}:")
        print(f"  {description}")
