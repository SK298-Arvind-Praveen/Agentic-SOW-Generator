"""
Company Research Agent - Simplified without prompt caching
"""
import json
import boto3
from typing import List

# Static Shellkode description
SHELLKODE_DESCRIPTION = "Shellkode specializes in developing advanced data and AI solutions for businesses. The company builds robust data foundations that transform raw inputs into actionable intelligence, creates self-improving machine learning systems, and offers AI-driven services to modernize applications and infrastructure for cloud environments. Shellkode's expertise lies in enhancing data processing, predictive modeling, and cloud migration capabilities."


class CompanyResearchAgent:
    """Simplified company research agent without prompt caching"""
    
    def __init__(self, config):
        self.config = config
        self.bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=config.AWS_REGION
        )
        
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
        prompt = f"""Write a professional 2-3 sentence description for {company_name} for a business proposal.

Requirements:
- Professional tone
- 40-80 words
- Focus on what they do

Generate ONLY the description:"""
        
        try:
            response = self.bedrock_client.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 256,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            
            # Track token usage
            from app.core.nodes import _track_tokens
            _track_tokens(response_body, f"Company Research: {company_name}")
            
            return response_body['content'][0]['text'].strip()
        except Exception as e:
            print(f"Error researching {company_name}: {e}")
            return f"Unable to research {company_name}"


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
