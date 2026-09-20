from app.ai.providers import (
    MockTranslationProvider,
    OpenAITranslationProvider,
    TranslationProvider,
)
from app.core.config import Settings, settings


class ProviderConfigurationError(RuntimeError):
    pass


def get_translation_provider(configuration: Settings = settings) -> TranslationProvider:
    provider_name = configuration.ai_provider.strip().lower()
    if provider_name == "mock":
        return MockTranslationProvider()
    if provider_name == "openai":
        api_key = configuration.openai_api_key or ""
        if not api_key:
            raise ProviderConfigurationError(
                "OPENAI_API_KEY is required when AI_PROVIDER=openai"
            )
        return OpenAITranslationProvider(
            api_key=api_key,
            model=configuration.openai_translation_model,
        )
    raise ProviderConfigurationError(
        f"Unsupported AI_PROVIDER: {configuration.ai_provider}"
    )
