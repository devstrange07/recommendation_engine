"""Shared OpenAI vision helper for describing images."""

from __future__ import annotations

import base64

from app.openai_client import chat_model, get_chat_client

VISION_SYSTEM = (
    "You are a product catalog analyst. Describe the content of this image factually. "
    "Focus on product names, features, prices, tables, and diagrams. "
    "Do NOT invent information not visible in the image."
)

MAX_IMAGES_PER_FILE = 8


def describe_image(image_bytes: bytes, *, mime: str = "image/png", context: str = "") -> str:
    client = get_chat_client()
    b64 = base64.b64encode(image_bytes).decode()
    user_parts: list[dict] = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "low"},
        },
    ]
    if context:
        user_parts.insert(0, {"type": "text", "text": context})

    resp = client.chat.completions.create(
        model=chat_model(),
        messages=[
            {"role": "system", "content": VISION_SYSTEM},
            {"role": "user", "content": user_parts},
        ],
        max_tokens=600,
    )
    return (resp.choices[0].message.content or "").strip()
