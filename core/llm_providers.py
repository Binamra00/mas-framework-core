# core/llm_providers.py
import requests
from abc import ABC, abstractmethod
from rich.console import Console
from core.config_manager import ConfigManager

# Initialize console for uniform UX loading states
console = Console()

# Universal defensive system prompt to prevent code truncation and hollowing
SYSTEM_PROMPT = (
    "You are a strict software architect execution engine. Your job is to make surgical "
    "modifications to code based on user requests. CRITICAL: You must return the ENTIRE "
    "file structure intact. Do not minimize code, do not omit existing methods, do not "
    "alter untouched logic, do not remove guardrails, and do not truncate imports. "
    "Return the complete, updated source code file from top to bottom with no conversational text."
)


class LLMProvider(ABC):
    """The formal Strategy interface for all LLM interactions."""
    @abstractmethod
    def generate_code(self, payload: str) -> str:
        pass


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/chat/completions"

    def generate_code(self, payload: str) -> str:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": payload}
            ],
            "temperature": 0.1
        }
        with console.status(f"[bold green]Contacting DeepSeek ({self.model})...[/bold green]", spinner="bouncingBar"):
            response = requests.post(self.api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.openai.com/v1/chat/completions"

    def generate_code(self, payload: str) -> str:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": payload}
            ],
            "temperature": 0.1
        }
        with console.status(f"[bold green]Contacting OpenAI ({self.model})...[/bold green]", spinner="bouncingBar"):
            response = requests.post(self.api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"

    def generate_code(self, payload: str) -> str:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        data = {
            "model": self.model,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": payload}],
            "temperature": 0.1
        }
        with console.status(f"[bold green]Contacting Anthropic ({self.model})...[/bold green]", spinner="bouncingBar"):
            response = requests.post(self.api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["content"][0]["text"]


class GoogleProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"

    def generate_code(self, payload: str) -> str:
        headers = {"Content-Type": "application/json"}
        data = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [{
                "role": "user",
                "parts": [{"text": payload}]
            }],
            "generationConfig": {
                "temperature": 0.1
            }
        }
        with console.status(f"[bold green]Contacting Google ({self.model})...[/bold green]", spinner="bouncingBar"):
            response = requests.post(self.api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]


class MetaProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.groq.com/openai/v1/chat/completions"

    def generate_code(self, payload: str) -> str:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": payload}
            ],
            "temperature": 0.1
        }
        with console.status(f"[bold green]Contacting Meta/Groq ({self.model})...[/bold green]", spinner="bouncingBar"):
            response = requests.post(self.api_url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class OllamaProvider(LLMProvider):
    def __init__(self, model: str):
        self.api_url = "http://localhost:11434/api/chat"
        self.model = model

    def generate_code(self, payload: str) -> str:
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": payload}
            ],
            "stream": False,
            "options": {"temperature": 0.1}
        }
        try:
            with console.status(f"[bold green]Running Local Inference ({self.model})...[/bold green]", spinner="bouncingBar"):
                response = requests.post(self.api_url, json=data)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except requests.exceptions.ConnectionError:
            raise ConnectionError("Could not connect to Ollama. Please ensure the app is running locally.")


class ProviderFactory:
    """Instantiates the correct LLM Provider based on user configuration."""
    @staticmethod
    def get_provider() -> LLMProvider:
        config = ConfigManager.load_config()
        provider_name = config.get("provider", "google")
        api_key = config.get("api_key", "")
        model_name = config.get("model", "")

        if provider_name == "deepseek":
            return DeepSeekProvider(api_key, model_name)
        elif provider_name == "openai":
            return OpenAIProvider(api_key, model_name)
        elif provider_name == "anthropic":
            return AnthropicProvider(api_key, model_name)
        elif provider_name == "google":
            return GoogleProvider(api_key, model_name)
        elif provider_name == "meta":
            return MetaProvider(api_key, model_name)
        elif provider_name == "ollama":
            return OllamaProvider(model_name)
        else:
            raise ValueError(f"Unknown provider: {provider_name}")