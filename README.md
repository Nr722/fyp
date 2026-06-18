# Agentic AI for Diplomacy Game

## Overview

An autonomous, LLM-driven multi-agent system designed to play the strategic board game *Diplomacy*. The framework simulates natural language negotiation, tactical coordination, and strategic decision-making, split into an isolated backend engine and an interactive frontend dashboard.

---

## Key Features

* **Natural Language Negotiation:** Autonomous agents capable of drafting, analyzing, and responding to complex alliance, peace, and betrayal proposals from other players.
* **Tactical Coordination:** LLM-driven strategic decision-making that translates high-level diplomatic agreements into concrete board movements and support actions.
* **Persistent Game State:** Seamless integration with PostgreSQL (Neon) to track player histories, board positions, and relationship matrices across game turns.
* **Real-time Visualization:** A Streamlit-based frontend dashboard allowing users to log in securely, view live board layouts, and monitor agent communications dynamically.

---

## Repository Structure

```text
├── backend/
│   ├── bot/          # LLM negotiation logic
|   ├── function_tools  # tactical decision-making logic of LLM
│   ├── .env.example     # Backend environment template
│   └── server.py        # Backend API/Engine entry point
│
├── frontend/
│   ├── frontend.py      # Streamlit UI for game visualization & user login
│   └── .env.example     # Frontend environment template
│
└── README.md
```

---

## Prerequisites

Before running the application, ensure you have the following configured:

1. **LLM API Key:** A Gemini API key from Google (the system uses `googlechatgenai`; switching to other providers requires updating the model initialization configuration).
2. **Database:** A running PostgreSQL instance (developed and tested using Neon Serverless Postgres).
3. **Environment Manager:** `uv` installed for fast, reproducible dependency management.

---

## Setup & Configuration

### Backend Setup

1. Navigate to the `backend/` directory.
2. Create a `.env` file using the template below:

```env
# backend/.env
GEMINI_API_KEY=your_gemini_api_key_here
DATABASE_URL=postgresql://user:password@neon_host/dbname
JWT_SECRET=your_super_secret_jwt_key
PORT=8000
```

### Frontend Setup

1. Navigate to the `frontend/` directory.
2. Create a `.env` file using the template below:

```env
# frontend/.env
BACKEND_URL=http://localhost:8000
```

---

## How to Run

Both components utilize `uv` to guarantee locked and synchronized dependency trees.

### 1. Start the Backend

```bash
cd backend
uv sync
uv run server.py
```

> Ensure your database migrations are applied or the schema is initialized on your Neon instance before launching the engine.

### 2. Start the Frontend

Open a new terminal window or tab, then run:

```bash
cd frontend
uv sync
uv run streamlit run frontend.py
```

Open the local URL provided by Streamlit (typically `http://localhost:8501`) in your browser to log in and interact with the game.
