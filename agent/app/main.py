from fastapi import FastAPI

app = FastAPI(title="Warehouse Safety Monitor Agent")


@app.get("/health")
def health():
    return {"status": "ok"}
