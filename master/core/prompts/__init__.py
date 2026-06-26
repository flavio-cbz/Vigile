from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str, **kwargs: str) -> str:
    """Load a prompt template from master/core/prompts/{name}.md and format it."""
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").format(**kwargs)
