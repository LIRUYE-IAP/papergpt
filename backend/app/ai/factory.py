from app.ai.providers import (
    MockTranslationProvider,
    OpenAITranslationProvider,
    TranslationProvider,
)
from app.ai.errors import AIAuthenticationError, AIUnavailableError, TranslationExecutionError
from app.core.config import Settings, settings


class ProviderConfigurationError(RuntimeError):
    def __init__(self, error: TranslationExecutionError) -> None:
        super().__init__(error.safe_message)
        self.error = error


def get_translation_provider(configuration: Settings = settings) -> TranslationProvider:
    provider_name = configuration.ai_provider.strip().lower()
    if provider_name == "mock":
        return MockTranslationProvider(
            failure_mode=configuration.papergpt_test_ai_failure
        )
    if provider_name == "openai":
        api_key = configuration.openai_api_key or ""
        if not api_key:
            raise ProviderConfigurationError(AIAuthenticationError())
        return OpenAITranslationProvider(
            api_key=api_key,
            model=configuration.openai_translation_model,
        )
    raise ProviderConfigurationError(AIUnavailableError())
