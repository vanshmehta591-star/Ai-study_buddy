"""
BobClient — thin wrapper around IBM watsonx.ai (Granite).

All LLM calls in the application go through this class so that
every service can be unit-tested by simply mocking `BobClient.generate`.
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()


class BobClient:
    """Wraps the ibm-watsonx-ai ModelInference API."""

    DEFAULT_MODEL = "ibm/granite-3-3-8b-instruct"

    def __init__(
        self,
        api_key: str | None = None,
        project_id: str | None = None,
        url: str | None = None,
        model_id: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("WATSONX_API_KEY", "")
        self._project_id = project_id or os.getenv("WATSONX_PROJECT_ID", "")
        self._url = url or os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
        self._model_id = model_id or self.DEFAULT_MODEL
        self._model = None  # lazy-initialised on first call

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self):
        """Lazy-initialise the ModelInference object."""
        if self._model is None:
            # Import here so that the rest of the app can be imported and
            # tested without ibm-watsonx-ai being configured.
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference

            credentials = Credentials(
                api_key=self._api_key,
                url=self._url,
            )
            self._model = ModelInference(
                model_id=self._model_id,
                credentials=credentials,
                project_id=self._project_id,
                params={
                    "max_new_tokens": 1024,
                    "temperature": 0.7,
                },
            )
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt: str, max_new_tokens: int = 1024) -> str:
        """Send *prompt* to the model and return the generated text.

        Parameters
        ----------
        prompt:
            The full prompt string to send.
        max_new_tokens:
            Override the default token limit for this call.

        Returns
        -------
        str
            The model's response text (stripped).

        Raises
        ------
        RuntimeError
            Wraps any underlying SDK/network error with a user-friendly message.
        """
        try:
            model = self._get_model()
            response = model.generate_text(
                prompt=prompt,
                params={"max_new_tokens": max_new_tokens},
            )
            return response.strip() if isinstance(response, str) else str(response).strip()
        except Exception as exc:
            raise RuntimeError(
                f"IBM watsonx.ai call failed: {exc}"
            ) from exc
