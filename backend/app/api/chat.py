"""Chat endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from openai import APIError, OpenAIError

from app.deps import get_tenant_id
from app.schemas import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def post_chat(body: ChatRequest, tenant_id: str = Depends(get_tenant_id)) -> ChatResponse:
    from app.rag.chat import run_chat_turn

    try:
        return run_chat_turn(body, tenant_id=tenant_id)
    except APIError as e:
        detail = getattr(e, "message", None) or str(e)
        status = getattr(e, "status_code", None) or 502
        raise HTTPException(status_code=int(status) if 400 <= int(status) < 600 else 502, detail=detail) from e
    except OpenAIError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
