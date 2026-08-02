from config import (VISION_PROVIDER, VISION_MODEL, GEMINI_API_KEY,
                   KIMI_API_KEY, DEEPSEEK_API_KEY)


def complete(prompt: str, system: str | None = None) -> str:
    """统一的文本生成接口，供笔记合并和问答 Agent 复用。"""
    if VISION_PROVIDER == "gemini":
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel(VISION_MODEL)
        full = (system + "\n\n" + prompt) if system else prompt
        return model.generate_content(full).text
    elif VISION_PROVIDER == "kimi":
        from openai import OpenAI
        client = OpenAI(api_key=KIMI_API_KEY, base_url="https://api.moonshot.cn/v1")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(model=VISION_MODEL, messages=messages)
        return resp.choices[0].message.content
    elif VISION_PROVIDER == "deepseek":
        from openai import OpenAI
        client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = client.chat.completions.create(model=VISION_MODEL, messages=messages)
        return resp.choices[0].message.content
    else:
        raise ValueError(f"未知 provider: {VISION_PROVIDER}")
