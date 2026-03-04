import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

DATA_PATH = Path("data.json")

def load_data():
    if not DATA_PATH.exists():
        return {"topics": []}
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    data = load_data()
    topics = data.get("topics", [])
    return templates.TemplateResponse("index.html", {"request": request, "topics": topics})

@app.get("/t/{slug}", response_class=HTMLResponse)
def topic_page(request: Request, slug: str):
    data = load_data()
    topics = data.get("topics", [])
    topic = next((t for t in topics if t.get("slug") == slug), None)
    if not topic:
        return HTMLResponse("Topic not found", status_code=404)
    return templates.TemplateResponse("topic.html", {"request": request, "topic": topic})
