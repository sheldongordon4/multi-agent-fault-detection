import logging
import random
import string

logger = logging.getLogger(__name__)

ALPHA_NUM = string.ascii_letters + string.digits


def generate_random_alphanum(length: int = 20) -> str:
    return "".join(random.choices(ALPHA_NUM, k=length))


def message_text(content) -> str:
    """
    The text of an LLM reply, whatever shape the provider returned.

    `ChatOpenAI` sets `.content` to a plain string. `ChatGoogleGenerativeAI`
    sets it to a LIST of content blocks - each a string, or a dict like
    {"type": "text", "text": "..."} - because Gemini replies are multi-part.

    That difference is quiet and destructive: `str(a_list)` produces a Python
    repr with single quotes, so JSON extraction finds braces but parses garbage,
    and the coordinator falls back to a heuristic ticket without an error. Both
    call sites normalise through here so neither can regress on its own.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)
