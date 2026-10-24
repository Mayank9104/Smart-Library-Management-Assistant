# AI-Powered Smart Library Management Assistant

Built for the **HCLTech Future Ready AI Engineer Hackathon**. Transforms a university library into an intelligent knowledge hub for discovery, research, circulation, and analytics.

## Tech Stack

- **Frontend:** Streamlit (`frontend/`)
- **Backend:** FastAPI (`backend/api/`, `backend/services/`, `backend/schemas/`)
- **Database:** SQLite + SQLAlchemy (`backend/models/`, `backend/db/`)
- **AI & Orchestration:** LangChain with **Groq API** (`llama-3.3-70b-versatile`) and **Local LLM** (`Ollama`) (`backend/ai/`, `backend/tools/`)
- **Vector Store & Embeddings:** ChromaDB + Local `sentence-transformers`
- **Analytics & Testing:** Pandas & Pytest (`tests/`)

## Quickstart

### 1. Setup Virtual Environment & Install Packages

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```
