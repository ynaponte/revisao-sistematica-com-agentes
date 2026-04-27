"""LLM factory with dual-mode support: Google Gemini or Ollama (local)."""

from __future__ import annotations

import os

from langchain_core.language_models import BaseChatModel


def get_llm(provider: str | None = None) -> BaseChatModel:
    """Create and return the configured LLM instance.

    Provider resolution order:
    1. Explicit ``provider`` argument ("gemini" or "ollama")
    2. ``LLM_PROVIDER`` environment variable
    3. Defaults to "gemini"

    Environment variables used:
    - ``LLM_PROVIDER``: "gemini", "ollama", or "vllm"
    - ``GOOGLE_API_KEY``: required for Gemini
    - ``OLLAMA_MODEL``: model name for Ollama (default: "llama3.1")
    - ``OLLAMA_BASE_URL``: Ollama server URL (default: "http://localhost:11434")
    - ``VLLM_MODEL``: model name for vLLM (default: "meta-llama/Llama-3-8b-instruct")
    - ``VLLM_BASE_URL``: vLLM server URL (default: "http://localhost:8000/v1")
    - ``VLLM_API_KEY``: vLLM API key (default: "none", some setups require it)
    """
    provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()

    if provider == "gemini":
        return _create_gemini()
    elif provider == "ollama":
        return _create_ollama()
    elif provider == "vllm":
        return _create_vllm()
    elif provider == "openai":
        return _create_openai()
    elif provider == "anthropic":
        return _create_anthropic()
    elif provider == "deepseek":
        return _create_deepseek()
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. Use 'gemini', 'ollama', 'vllm', 'openai', 'anthropic', or 'deepseek'."
        )


def _create_gemini() -> BaseChatModel:
    """Create a Google Gemini chat model."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY environment variable is required for Gemini provider. "
            "Set it in your .env file or environment."
        )

    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        google_api_key=api_key,
        temperature=0.1,
    )


def _create_ollama() -> BaseChatModel:
    """Create an Ollama local chat model."""
    from langchain_ollama import ChatOllama

    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    
    is_docker = os.path.exists("/.dockerenv")
    default_host = "host.docker.internal" if is_docker else "localhost"
    base_url = os.getenv("OLLAMA_BASE_URL", f"http://{default_host}:11434")

    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=0.1,
    )


def _create_vllm() -> BaseChatModel:
    """Create a vLLM chat model via the OpenAI compatibility layer."""
    from langchain_openai import ChatOpenAI

    model = os.getenv("VLLM_MODEL", "meta-llama/Llama-3-8b-instruct")
    
    is_docker = os.path.exists("/.dockerenv")
    default_host = "host.docker.internal" if is_docker else "localhost"
    base_url = os.getenv("VLLM_BASE_URL", f"http://{default_host}:8000/v1")
    api_key = os.getenv("VLLM_API_KEY", "EMPTY")  # vLLM will accept any string if no auth is configured

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.1,
    )


def _create_openai() -> BaseChatModel:
    """Create an OpenAI chat model."""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY environment variable is required for OpenAI provider.")

    return ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        api_key=api_key,
        temperature=0.1,
    )


def _create_anthropic() -> BaseChatModel:
    """Create an Anthropic Claude chat model."""
    from langchain_anthropic import ChatAnthropic

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY environment variable is required for Anthropic provider.")

    return ChatAnthropic(
        model_name=os.getenv("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
        api_key=api_key,
        temperature=0.1,
    )


def _create_deepseek() -> BaseChatModel:
    """Create a DeepSeek chat model."""
    from langchain_deepseek import ChatDeepSeek

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise EnvironmentError("DEEPSEEK_API_KEY environment variable is required for DeepSeek provider.")

    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=api_key,
        api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        temperature=0.1,
    )
