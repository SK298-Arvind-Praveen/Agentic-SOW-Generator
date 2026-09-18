"""
Company Research Agent - Simplified without prompt caching
"""
import boto3
import re
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
        prompt += """

Before responding, silently check that the draft contains exactly two non-empty paragraphs,
contains no heading or list, discusses only the company, and contains none of the forbidden
engagement language above. Correct the draft before returning it."""
        
        best = ""
        for attempt in range(3):
            attempt_prompt = prompt
            if best:
                detected = "; ".join(self._company_profile_issues(best))
                attempt_prompt += (
                    "\n\nSelf-review the previous draft against the contract. The deterministic "
                    f"validator found: {detected}. Rewrite it, retaining only supported company "
                    "facts. Silently verify every finding is resolved before returning only the "
                    "two corrected paragraphs:\n\n" + best[:3000]
                )
            try:
                result = self.llm.generate(
                    attempt_prompt,
                    task="fast",
                    max_tokens=400,
                    temperature=0.3,
                    call_name=f"Company Context: {company_name} attempt {attempt + 1}",
                    fallback_model_id=getattr(self.config, "ANALYSIS_MODEL_ID", None),
                )
                best = result.text.strip()
                if not self._company_profile_issues(best):
                    return best
            except Exception as e:
                print(f"Error researching {company_name}: {e}")
                break
        # Research is enrichment only. The SOW writer can use source-grounded
        # company context even when this optional profile pass is imperfect.
        return best

    @staticmethod
    def _company_profile_issues(content: str) -> List[str]:
        issues: List[str] = []
        paragraphs = [
            item.strip() for item in re.split(r"\n\s*\n", content or "") if item.strip()
        ]
        if len(paragraphs) != 2:
            issues.append(f"expected exactly two paragraphs, found {len(paragraphs)}")
        if re.search(
            r"(?i)\b(?:statement of work|this engagement|project scope|project objective|"
            r"proposed solution|shellkode(?:'s)? involvement)\b",
            content or "",
        ):
            issues.append("contains project or engagement language")
        if re.search(r"(?m)^\s*(?:#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|\|)", content or ""):
            issues.append("contains a heading, list or table")
        return issues


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
