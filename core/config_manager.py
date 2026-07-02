# core/config_manager.py
import json
from pathlib import Path
from typing import Dict, Any

class ConfigManager:
    CONFIG_PATH = Path.home() / ".mas-framework" / "config.json"

    @classmethod
    def run_setup_wizard(cls) -> None:
        print("\n--- MAS Framework Configuration ---")
        print("Select your preferred AI Provider:")
        print("  1. DeepSeek")
        print("  2. OpenAI")
        print("  3. Anthropic")
        print("  4. Google (Gemini)")
        print("  5. Meta (via Groq/Together)")
        print("  6. Ollama (Local/Offline)")

        choice = input("\nEnter choice (1-6): ").strip()
        provider_map = {
            "1": "deepseek", "2": "openai", "3": "anthropic",
            "4": "google", "5": "meta", "6": "ollama"
        }
        provider = provider_map.get(choice, "google")

        api_key = ""
        if provider != "ollama":
            api_key = input(f"Enter your {provider.capitalize()} API Key: ").strip()

        print(f"\nEnter the exact model name you want to use.")
        print("(e.g., 'gemini-1.5-pro', 'claude-3-5-sonnet-20240620', 'llama3-70b-8192')")
        model_name = input("Model: ").strip()

        cls.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(cls.CONFIG_PATH, "w") as f:
            json.dump({
                "provider": provider,
                "api_key": api_key,
                "model": model_name
            }, f)

        print(f"\n[MAS] Configuration saved! Using {provider.capitalize()} with model: {model_name}")

    @classmethod
    def load_config(cls) -> Dict[str, Any]:
        if not cls.CONFIG_PATH.exists():
            raise FileNotFoundError("MAS Framework not configured. Run 'mas configure' first.")
        with open(cls.CONFIG_PATH, "r") as f:
            return json.load(f)