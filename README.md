# Voker Agent API

Minimal FastAPI starter with LangChain, LangGraph, and `.env` support.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -U pip
pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> for the interactive API docs.
