"""
Model Selector - Dynamically selects LLM models based on project complexity.
"""
import logging

logger = logging.getLogger(__name__)


class ModelSelector:
    """Selects the most cost-effective models for each agent role."""

    # Model tiers using real Opencode Zen model IDs.
    # Higher tier = stronger reasoning (and higher cost).
    MODELS = {
        "ceo": {
            "high": {"name": "claude-opus-4-5", "provider": "opencode-go"},
            "medium": {"name": "claude-sonnet-4-5", "provider": "opencode-go"},
            "low": {"name": "claude-haiku-4-5", "provider": "opencode-go"},
        },
        "manager": {
            "high": {"name": "claude-sonnet-4-5", "provider": "opencode-go"},
            "medium": {"name": "gpt-5.1", "provider": "opencode-go"},
            "low": {"name": "claude-haiku-4-5", "provider": "opencode-go"},
        },
        "worker": {
            "high": {"name": "gpt-5.1-codex", "provider": "opencode-go"},
            "medium": {"name": "gpt-5.1", "provider": "opencode-go"},
            "low": {"name": "claude-haiku-4-5", "provider": "opencode-go"},
        },
        "efficiency": {
            "high": {"name": "claude-sonnet-4-5", "provider": "opencode-go"},
            "medium": {"name": "gpt-5.1", "provider": "opencode-go"},
            "low": {"name": "claude-haiku-4-5", "provider": "opencode-go"},
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

    def select_fixed_model(self, model_name: str) -> dict:
        """
        Force a specific model for every role (user choice overrides auto).
        Validates the model exists in the Opencode catalog.
        """
        # Known Opencode Zen models (from /zen/v1/models)
        KNOWN = {
            "claude-opus-4-5", "claude-sonnet-4-5", "claude-haiku-4-5",
            "claude-sonnet-4", "claude-haiku-3-5",
            "gpt-5.1", "gpt-5.1-codex", "gpt-5.1-codex-max", "gpt-5",
            "gpt-5-codex", "gpt-5-nano",
            "kimi-k2", "glm-4.6", "qwen3-coder", "grok-code",
            "gemini-3-pro", "gemini-3-flash", "minimax-m2.1-free",
        }
        if model_name not in KNOWN:
            logger.warning(f"Unknown model '{model_name}', falling back to auto")
            return self.select_models(project_size=100, complexity_score=0.3)

        logger.info(f"Model forced by user for all roles: {model_name}")
        return {
            role: {"name": model_name, "provider": "opencode-go", "tier": "user"}
            for role in ("ceo", "manager", "worker", "efficiency")
        }

    def list_models(self) -> list[str]:
        """Return the selectable models for the UI dropdown."""
        return [
            "claude-opus-4-5",
            "claude-sonnet-4-5",
            "claude-haiku-4-5",
            "gpt-5.1-codex",
            "gpt-5.1",
            "gpt-5-nano",
            "kimi-k2",
            "glm-4.6",
            "qwen3-coder",
            "gemini-3-pro",
            "gemini-3-flash",
        ]
