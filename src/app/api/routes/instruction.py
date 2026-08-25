import json
from json import JSONDecodeError
from typing import Any

from fastapi import APIRouter, HTTPException, status
from groq import Groq

from src.app.core.config import get_settings
from src.app.schemas.voice import InstructionPayload, InstructionRequest

router = APIRouter(tags=["instruction"])


@router.get("/groq-hello")
def groq_hello_world() -> dict[str, str]:
    """Endpoint de prueba equivalente al ejemplo de SDK: retorna la respuesta del modelo."""
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key, timeout=settings.request_timeout_seconds)

    try:
        chat_completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": "Eres un asistente util y conciso."},
                {"role": "user", "content": "Dime hola mundo."},
            ],
        )
    except Exception as exc:  # pragma: no cover - depende de red/servicio externo
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq request failed: {exc}",
        ) from exc

    message = (
        chat_completion.choices[0].message.content
        if chat_completion.choices and chat_completion.choices[0].message
        else ""
    )
    return {"message": message or ""}


@router.post("/instruction", response_model=InstructionPayload)
def route_instruction(
    payload: InstructionRequest,
) -> InstructionPayload:
    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key, timeout=settings.request_timeout_seconds)

    # Forzamos salida JSON para que el frontend pueda ejecutar routing sin heurísticas locales.
    system_prompt = (
        "You are an API router for a TODO app. "
        "Return only one valid JSON object with keys: endpoint, method, params. "
        "Allowed endpoints/methods: "
        "GET /tasks with empty params, "
        "POST /tasks with params {title: string, done?: boolean}, "
        "PUT /tasks/{id} with params {task_id: int, title: string, done: boolean}, "
        "PATCH /tasks/{id} with params {task_id: int, title?: string, done?: boolean}, "
        "DELETE /tasks/{id} with params {task_id: int}. "
        "Do not include markdown, explanations, or extra keys."
    )

    try:
        response = client.chat.completions.create(
            model=settings.groq_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": payload.transcription,
                },
            ],
        )
    except Exception as exc:  # pragma: no cover - depende de red/servicio externo
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq request failed: {exc}",
        ) from exc

    raw_content = response.choices[0].message.content if response.choices else ""
    parsed = _parse_llm_json(raw_content)

    try:
        return InstructionPayload.model_validate(parsed)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="LLM response did not match InstructionPayload schema",
        ) from exc


def _parse_llm_json(raw_content: str | None) -> dict[str, Any]:
    if not raw_content:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq returned an empty response",
        )

    content = raw_content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()

    try:
        parsed = json.loads(content)
    except JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq response was not valid JSON",
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Groq response JSON must be an object",
        )

    return parsed
