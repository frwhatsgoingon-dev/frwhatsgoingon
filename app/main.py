from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <h1>frwhatsgoingon</h1>
    <p>Breaking news explained for students.</p>
    """
