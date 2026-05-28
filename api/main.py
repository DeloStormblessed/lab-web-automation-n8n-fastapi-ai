from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import httpx
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Lab Automatización API")

# In-memory storage
_tareas_db: List[dict] = []
_tarea_counter = 0

_usuarios_db = {
    1: {"id": 1, "nombre": "Ana García", "email": "ana@example.com", "plan": "premium"},
    2: {"id": 2, "nombre": "Carlos López", "email": "carlos@example.com", "plan": "basic"},
    42: {"id": 42, "nombre": "María Martínez", "email": "maria@example.com", "plan": "premium"},
}


class TareaEntrada(BaseModel):
    titulo: str
    prioridad: str = "media"
    descripcion: Optional[str] = None
    completada: bool = False


class ChatRequest(BaseModel):
    mensaje: str


async def notificar_n8n(webhook_url: str, payload: dict):
    if not webhook_url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(webhook_url, json=payload)
    except Exception:
        pass  # N8N no debe bloquear la respuesta principal


def guardar_en_db(tarea: TareaEntrada) -> dict:
    global _tarea_counter
    _tarea_counter += 1
    nueva = {
        "id": _tarea_counter,
        "titulo": tarea.titulo,
        "prioridad": tarea.prioridad,
        "descripcion": tarea.descripcion,
        "completada": tarea.completada,
        "created_at": datetime.now().isoformat(),
    }
    _tareas_db.append(nueva)
    return nueva


@app.post("/tareas", status_code=201)
async def crear_tarea(tarea: TareaEntrada, background_tasks: BackgroundTasks):
    nueva = guardar_en_db(tarea)
    background_tasks.add_task(
        notificar_n8n,
        os.getenv("N8N_WEBHOOK_TAREAS", ""),
        {"evento": "tarea_creada", "tarea": nueva},
    )
    return {"ok": True, "data": nueva}


@app.get("/tareas")
async def listar_tareas(completada: Optional[bool] = None):
    if completada is not None:
        return [t for t in _tareas_db if t["completada"] == completada]
    return _tareas_db


@app.get("/usuarios/{usuario_id}")
async def obtener_usuario(usuario_id: int):
    usuario = _usuarios_db.get(usuario_id)
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return usuario


@app.post("/api/chat")
async def chat(request: ChatRequest):
    from groq import Groq

    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": request.mensaje}],
        max_tokens=1024,
    )
    return {"respuesta": completion.choices[0].message.content}


@app.get("/health")
async def health():
    n8n_url = os.getenv("N8N_WEBHOOK_TAREAS", "")
    n8n_ok = False
    if n8n_url:
        try:
            from urllib.parse import urlparse
            base = f"{urlparse(n8n_url).scheme}://{urlparse(n8n_url).netloc}"
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{base}/healthz")
                n8n_ok = r.status_code < 500
        except Exception:
            pass
    return {"status": "ok", "n8n_reachable": n8n_ok}
