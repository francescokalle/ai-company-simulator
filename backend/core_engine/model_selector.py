"""
Model Selector - Dynamically selects LLM models based on project complexity.
"""
import logging

logger = logging.getLogger(__name__)


class ModelSelector:
    """Selects the most cost-effective models for each agent role."""

    # Model tiers: (name, provider, cost_tier, capability_tier)
    MODELS = {
        "ceo": {
            "high": {"name": "claude-sonnet-4", "provider": "opencode-go"},
            "medium": {"name": "gpt-4o", "provider": "opencode-go"},
            "low": {"name": "gemini-2.0-flash", "provider": "opencode-go"},
        },
        "manager": {
            "high": {"name": "claude-sonnet-4", "provider": "opencode-go"},
            "medium": {"name": "gpt-4o-mini", "provider": "opencode-go"},
            "low": {"name": "gemini-2.0-flash", "provider": "opencode-go"},
        },
        "worker": {
            "high": {"name": "gpt-4o", "provider": "opencode-go"},
            "medium": {"name": "gpt-4o-mini", "provider": "opencode-go"},
            "low": {"name": "gemini-2.0-flash", "provider": "opencode-go"},
        },
        "efficiency": {
            "high": {"name": "claude-sonnet-4", "provider": "opencode-go"},
            "medium": {"name": "gpt-4o-mini", "provider": "opencode-go"},
            "low": {"name": "gemini-2.0-flash", "provider": "opencode-go"},
        },
    }

    def select_models(self, project_size: int, complexity_score: float) -> dict:
        """
        Select models based on project characteristics.
        
        Args:
            project_size: Number of files in the project.
            complexity_score: 0.0-1.0 complexity rating.
            
        Returns:
            Dict mapping role -> model config.
        """
        # Determine tier
        if complexity_score > 0.7 or project_size > 300:
            tier = "high"
        elif complexity_score > 0.3 or project_size > 100:
            tier = "medium"
        else:
            tier = "low"

        selected = {}
        for role, tiers in self.MODELS.items():
            selected[role] = {
                **tiers[tier],
                "tier": tier,
            }

        logger.info(f"Model selection: tier={tier}, size={project_size}, complexity={complexity_score}")
        return selected
