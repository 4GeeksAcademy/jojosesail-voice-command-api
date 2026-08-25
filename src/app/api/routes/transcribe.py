import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, UploadFile, status
from groq import Groq
from starlette.datastructures import UploadFile as StarletteUploadFile

from src.app.api.routes.instruction import route_instruction
from src.app.api.routes.tasks import (
    create_task,
    delete_task,
    get_tasks,
    replace_task,
    update_task,
)
from src.app.core.config import get_settings
from src.app.schemas.voice import (
    InstructionRequest,
    TaskCreate,
    TaskReplace,
    TaskUpdate,
    TranscribeFlowResponse,
)
from src.app.utils.language import normalize_transcription_language

router = APIRouter(tags=["transcribe"])
_TASK_ID_IN_PATH = re.compile(r"^/tasks/(?P<task_id>\d+)$")


@router.get("/")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/transcribe", response_model=TranscribeFlowResponse)
async def transcribe_and_run_flow(request: Request) -> TranscribeFlowResponse:
    transcription = await _resolve_transcription(request)
    instruction = route_instruction(InstructionRequest(transcription=transcription))
    result = _execute_instruction(instruction.endpoint, instruction.method, instruction.params)

    return TranscribeFlowResponse(
        transcription=transcription,
        instruction=instruction,
        result=result,
    )


async def _resolve_transcription(request: Request) -> str:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload = InstructionRequest.model_validate(await request.json())
        return payload.transcription

    if "multipart/form-data" in content_type:
        form_data = await request.form()
        upload = form_data.get("file")
        language = normalize_transcription_language(form_data.get("language"))

        if not isinstance(upload, (UploadFile, StarletteUploadFile)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing audio file in multipart field 'file'.",
            )

        return await _transcribe_audio(upload, language)

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported content type. Use application/json or multipart/form-data.",
    )


async def _transcribe_audio(upload: UploadFile, language: str | None) -> str:
    audio_bytes = await upload.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty.",
        )

    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key, timeout=settings.request_timeout_seconds)

    try:
        transcription = client.audio.transcriptions.create(
            file=(upload.filename or "command.webm", audio_bytes),
            model=settings.groq_transcription_model,
            language=language,
            response_format="verbose_json",
        )
    except Exception as exc:  # pragma: no cover - depende de red/servicio externo
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Groq transcription failed: {exc}",
        ) from exc

    text = (getattr(transcription, "text", None) or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Transcription service returned empty text.",
        )
    return text


def _extract_task_id(endpoint: str, params: dict[str, Any]) -> int:
    raw_id = params.get("task_id")
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str) and raw_id.isdigit():
        return int(raw_id)

    matched = _TASK_ID_IN_PATH.fullmatch(endpoint)
    if matched:
        return int(matched.group("task_id"))

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Instruction requires a valid task_id for this method.",
    )


def _execute_instruction(endpoint: str, method: str, params: dict[str, Any]) -> Any:
    normalized_method = method.upper()
    normalized_endpoint = endpoint.strip()

    if normalized_method == "GET" and normalized_endpoint == "/tasks":
        return get_tasks()

    if normalized_method == "POST" and normalized_endpoint == "/tasks":
        payload = TaskCreate.model_validate(params)
        return create_task(payload)

    if normalized_method == "PUT" and normalized_endpoint.startswith("/tasks"):
        task_id = _extract_task_id(normalized_endpoint, params)
        payload = TaskReplace.model_validate(params)
        return replace_task(task_id=task_id, payload=payload)

    if normalized_method == "PATCH" and normalized_endpoint.startswith("/tasks"):
        task_id = _extract_task_id(normalized_endpoint, params)
        payload = TaskUpdate.model_validate(params)
        return update_task(task_id=task_id, payload=payload)

    if normalized_method == "DELETE" and normalized_endpoint.startswith("/tasks"):
        task_id = _extract_task_id(normalized_endpoint, params)
        return delete_task(task_id)

    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="Unsupported instruction route returned by LLM.",
    )
