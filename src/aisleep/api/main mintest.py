from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def test_endpoint():
    return {"status": "working"}
