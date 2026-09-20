from openai import OpenAI

from app.ai.prompts import (
    ACADEMIC_TRANSLATION_INSTRUCTIONS,
    build_academic_translation_input,
)
from app.ai.providers.base import TranslationProvider, TranslationProviderError
from app.ai.types import TranslationRequest, TranslationResult


class OpenAITranslationProvider(TranslationProvider):
    name = "openai"

    def __init__(self, *, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")
        self.model = model
        self._client = OpenAI(api_key=api_key)

    def translate(self, request: TranslationRequest) -> TranslationResult:
        try:
            response = self._client.responses.create(
                model=self.model,
                instructions=ACADEMIC_TRANSLATION_INSTRUCTIONS,
                input=build_academic_translation_input(request),
                store=False,
            )
        except Exception as exc:
            raise TranslationProviderError("OpenAI translation request failed") from exc

        translated_text = response.output_text.strip()
        if not translated_text:
            raise TranslationProviderError("OpenAI returned an empty translation")
        return TranslationResult(
            translated_text=translated_text,
            provider=self.name,
            model=self.model,
        )
