from typing import Final

from fastapi import APIRouter, HTTPException, status

from src.app.schemas.voice import Task, TaskCreate, TaskReplace, TaskUpdate

router = APIRouter(prefix="/tasks", tags=["tasks"])

# Almacén temporal en memoria (se reinicia al reiniciar el proceso).
tasks: list[Task] = [
    Task(id=1, title="Configurar proyecto FastAPI", done=True),
    Task(id=2, title="Implementar endpoint de tareas", done=False),
]

NOT_FOUND_DETAIL: Final[str] = "Task not found"


@router.get("", response_model=list[Task])
def get_tasks() -> list[Task]:
    # Devuelve una copia para evitar mutaciones externas sobre el almacén.
    return list(tasks)


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> Task:
    next_id = max((task.id for task in tasks), default=0) + 1
    new_task = Task(id=next_id, title=payload.title, done=payload.done)
    tasks.append(new_task)
    return new_task


@router.put("/{task_id}", response_model=Task)
def replace_task(
    task_id: int,
    payload: TaskReplace,
) -> Task:
    index = _find_task_index(task_id)
    replaced_task = Task(id=task_id, title=payload.title, done=payload.done)
    tasks[index] = replaced_task
    return replaced_task


@router.patch("/{task_id}", response_model=Task)
def update_task(
    task_id: int,
    payload: TaskUpdate,
) -> Task:
    index = _find_task_index(task_id)
    current = tasks[index]
    updated_task = Task(
        id=current.id,
        title=payload.title if payload.title is not None else current.title,
        done=payload.done if payload.done is not None else current.done,
    )
    tasks[index] = updated_task
    return updated_task


@router.delete("/{task_id}")
def delete_task(task_id: int) -> dict[str, str]:
    index = _find_task_index(task_id)
    deleted_task = tasks.pop(index)
    return {"message": f"Task {deleted_task.id} deleted"}


def _find_task_index(task_id: int) -> int:
    """Busca el índice de una tarea por ID o lanza 404 si no existe."""
    for index, task in enumerate(tasks):
        if task.id == task_id:
            return index

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=NOT_FOUND_DETAIL)
