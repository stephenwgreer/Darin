"""
Prompt Processor
Manages prompt templates and analysis routing for the new WebSocket architecture.
Adapts existing prompt registry for real-time streaming and analysis.
"""

from typing import Dict, List, Optional, Any
from dataclasses import asdict

# Import existing prompt registry
from prompts.registry import PROMPT_REGISTRY, PromptConfig, get_prompt_config_by_id


class PromptProcessor:
    """
    Processes prompts and manages analysis types for WebSocket architecture.
    Provides a clean interface to the existing prompt system.
    """
    
    def __init__(self):
        """Initialize prompt processor with existing registry"""
        self.prompt_registry = PROMPT_REGISTRY
        self.prompt_lookup = {config.id: config for config in PROMPT_REGISTRY}
        
        print(f"✅ Prompt processor initialized with {len(PROMPT_REGISTRY)} prompts")
    
    def get_prompt_config(self, prompt_id: str) -> Optional[PromptConfig]:
        """
        Get prompt configuration by ID.
        
        Args:
            prompt_id: Unique prompt identifier
            
        Returns:
            PromptConfig: Prompt configuration or None if not found
        """
        return self.prompt_lookup.get(prompt_id)
    
    def get_prompt_template(self, prompt_id: str) -> Optional[str]:
        """
        Get prompt template string by ID.
        
        Args:
            prompt_id: Unique prompt identifier
            
        Returns:
            str: Prompt template string or None if not found
        """
        config = self.get_prompt_config(prompt_id)
        return config.template if config else None
    
    def get_all_prompts(self) -> List[Dict[str, Any]]:
        """
        Get all available prompts for frontend.
        
        Returns:
            List[Dict]: List of prompt configurations as dictionaries
        """
        return [
            {
                "id": config.id,
                "button_text": config.button_text,
                "output_title": config.output_title,
                "template_type": config.template_type
            }
            for config in self.prompt_registry
        ]
    
    def get_prompts_by_category(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get prompts organized by category for frontend UI.
        
        Returns:
            Dict: Prompts organized by category
        """
        categories = {
            "transcript_processing": [],
            "analysis": [],
            "logic_frameworks": [],
            "specialized": []
        }
        
        # Categorize prompts based on their characteristics
        for config in self.prompt_registry:
            prompt_info = {
                "id": config.id,
                "button_text": config.button_text,
                "output_title": config.output_title,
                "template_type": config.template_type
            }
            
            # Categorize based on prompt ID patterns
            if config.id in ["topic_summary", "meeting_summary", "sentiment_analysis"]:
                categories["transcript_processing"].append(prompt_info)
            elif config.id in ["scqa", "hypothesis_driven", "first_principles", "issue_tree", "reframing"]:
                categories["logic_frameworks"].append(prompt_info)
            elif config.id in ["company_fit", "fact_check", "answer_question"]:
                categories["specialized"].append(prompt_info)
            else:
                categories["analysis"].append(prompt_info)
        
        return categories
    
    def validate_prompt_request(self, prompt_id: str, transcript: str) -> tuple[bool, Optional[str]]:
        """
        Validate a prompt analysis request.
        
        Args:
            prompt_id: Prompt identifier
            transcript: Transcript text to analyze
            
        Returns:
            tuple: (is_valid, error_message)
        """
        # Check if prompt exists
        if prompt_id not in self.prompt_lookup:
            return False, f"Unknown prompt ID: {prompt_id}"
        
        # Check if transcript is provided
        if not transcript or not transcript.strip():
            return False, "No transcript provided for analysis"
        
        # Check transcript length (basic validation)
        if len(transcript.strip()) < 10:
            return False, "Transcript too short for meaningful analysis"
        
        # All validations passed
        return True, None
    
    def format_prompt(self, prompt_id: str, transcript: str, **kwargs) -> Optional[str]:
        """
        Format a prompt template with transcript and additional parameters.
        
        Args:
            prompt_id: Prompt identifier
            transcript: Transcript text
            **kwargs: Additional template parameters
            
        Returns:
            str: Formatted prompt or None if prompt not found
        """
        template = self.get_prompt_template(prompt_id)
        if not template:
            return None
        
        try:
            # Format template with transcript and any additional parameters
            formatted_prompt = template.format(transcript=transcript, **kwargs)
            return formatted_prompt
        except KeyError as e:
            print(f"❌ Missing template parameter: {e}")
            return None
        except Exception as e:
            print(f"❌ Error formatting prompt: {e}")
            return None
    
    def get_streaming_info(self, prompt_id: str) -> Dict[str, Any]:
        """
        Get streaming information for a prompt.
        
        Args:
            prompt_id: Prompt identifier
            
        Returns:
            Dict: Streaming configuration information
        """
        config = self.get_prompt_config(prompt_id)
        if not config:
            return {"supports_streaming": False}
        
        # All prompts support streaming in the new architecture
        return {
            "supports_streaming": True,
            "template_type": config.template_type,
            "output_title": config.output_title,
            "expected_format": self._get_expected_format(config.template_type)
        }
    
    def _get_expected_format(self, template_type: str) -> str:
        """
        Get expected output format for a template type.
        
        Args:
            template_type: Template type identifier
            
        Returns:
            str: Expected format description
        """
        format_map = {
            "sentiment-analysis": "Overall sentiment + list items",
            "fact-check": "Structured fact-check items with ratings",
            "problem-solving": "Structured analysis with sections",
            "scqa": "SCQA framework sections",
            "hypothesis-driven": "Hypothesis analysis sections",
            "first-principles": "First principles breakdown sections",
            "fill-gaps": "Core thinking + gaps + recommendations",
            "brainstorm": "Challenge questions + alternative frames + provocative ideas",
            "company-fit": "Key topics + SAS Viya connections + missing considerations",
            "answer-question": "Answer + rationale + examples",
            "reframing": "Reframed statement + supporting points"
        }
        
        return format_map.get(template_type, "List items")
    
    def get_prompt_stats(self) -> Dict[str, Any]:
        """
        Get statistics about available prompts.
        
        Returns:
            Dict: Prompt statistics
        """
        categories = self.get_prompts_by_category()
        
        return {
            "total_prompts": len(self.prompt_registry),
            "categories": {
                category: len(prompts) 
                for category, prompts in categories.items()
            },
            "template_types": list(set(config.template_type for config in self.prompt_registry)),
            "prompt_ids": list(self.prompt_lookup.keys())
        }
    
    def search_prompts(self, query: str) -> List[Dict[str, Any]]:
        """
        Search prompts by text query.
        
        Args:
            query: Search query string
            
        Returns:
            List[Dict]: Matching prompt configurations
        """
        query_lower = query.lower()
        matching_prompts = []
        
        for config in self.prompt_registry:
            # Search in button text, output title, and prompt ID
            if (query_lower in config.button_text.lower() or 
                query_lower in config.output_title.lower() or 
                query_lower in config.id.lower()):
                
                matching_prompts.append({
                    "id": config.id,
                    "button_text": config.button_text,
                    "output_title": config.output_title,
                    "template_type": config.template_type,
                    "relevance_score": self._calculate_relevance(config, query_lower)
                })
        
        # Sort by relevance score
        matching_prompts.sort(key=lambda x: x["relevance_score"], reverse=True)
        
        return matching_prompts
    
    def _calculate_relevance(self, config: PromptConfig, query: str) -> float:
        """
        Calculate relevance score for search query.
        
        Args:
            config: Prompt configuration
            query: Search query (lowercase)
            
        Returns:
            float: Relevance score (higher = more relevant)
        """
        score = 0.0
        
        # Exact match in ID gets highest score
        if query == config.id.lower():
            score += 10.0
        
        # Exact match in button text
        if query == config.button_text.lower():
            score += 8.0
        
        # Partial matches
        if query in config.button_text.lower():
            score += 5.0
        
        if query in config.output_title.lower():
            score += 3.0
        
        if query in config.id.lower():
            score += 2.0
        
        return score
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get prompt processor status.
        
        Returns:
            Dict: Status information
        """
        return {
            "prompts_loaded": len(self.prompt_registry),
            "categories_available": len(self.get_prompts_by_category()),
            "registry_source": "prompts.registry",
            "template_types": len(set(config.template_type for config in self.prompt_registry))
        }