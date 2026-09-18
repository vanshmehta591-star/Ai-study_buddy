# AI Study Buddy

An AI-powered study assistant built with Python, Streamlit, and IBM watsonx.ai (Granite).

## Features

- 📄 **Document Upload** — Upload PDF or TXT notes/syllabus (max 5 MB); text is extracted and split into named topics.
- 💡 **Explain Like I'm 10** — Get a simple, jargon-free explanation of any topic via IBM Granite.
- 🧠 **Quiz Mode** — Generate 5 multiple-choice questions per topic, answer one at a time, and get a final score.
- 📅 **Revision Planner** — Provide an exam date and select topics; get a structured day-by-day revision plan.
- 💬 **Doubt Chat** — Ask questions grounded in your uploaded document; clearly states when the answer isn't in the material.

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in your IBM watsonx.ai credentials
```

### 3. Run the app

```bash
streamlit run app.py
```

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
study_buddy/
├── app.py                        # Streamlit UI
├── services/
│   ├── bob_client.py             # IBM watsonx.ai wrapper
│   ├── document_service.py       # Upload, extract, chunk
│   ├── quiz_service.py           # Quiz generation & scoring
│   ├── revision_service.py       # Revision plan generation
│   ├── chat_service.py           # Grounded doubt-solving chat
│   └── explanation_service.py   # ELI-10 explanations
├── tests/                        # pytest unit tests (all Bob calls mocked)
├── data/                         # JSON persistence
├── .env.example                  # Credentials template
└── requirements.txt
```

## Environment Variables

| Variable             | Description                          |
|----------------------|--------------------------------------|
| `WATSONX_API_KEY`    | IBM Cloud API key                    |
| `WATSONX_PROJECT_ID` | watsonx.ai project ID                |
| `WATSONX_URL`        | watsonx.ai endpoint (region-based)   |
