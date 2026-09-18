"""
app.py — AI Study Buddy Streamlit UI

All business logic lives in the service layer.
This file only calls service methods and renders the results.
"""
from __future__ import annotations

import datetime
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Page config (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Study Buddy",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Service imports (deferred so page config runs first)
# ---------------------------------------------------------------------------
from services.bob_client import BobClient
from services.chat_service import ChatService, ChatValidationError
from services.document_service import DocumentService, DocumentValidationError
from services.explanation_service import ExplanationService
from services.quiz_service import QuizService
from services.revision_service import RevisionService, RevisionValidationError


# ---------------------------------------------------------------------------
# Cached service instances (one per session)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_services():
    bob = BobClient()
    return {
        "document": DocumentService(),
        "explanation": ExplanationService(bob),
        "quiz": QuizService(bob),
        "revision": RevisionService(bob),
        "chat": ChatService(bob),
    }


services = get_services()
doc_svc: DocumentService = services["document"]
exp_svc: ExplanationService = services["explanation"]
quiz_svc: QuizService = services["quiz"]
rev_svc: RevisionService = services["revision"]
chat_svc: ChatService = services["chat"]


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def _init_state():
    defaults = {
        "active_doc": None,          # currently loaded document record
        "quiz_state": None,          # {"quiz": {...}, "current_q": int, "answers": [], "finished": bool}
        "chat_history": [],          # [{"role": "user"|"assistant", "content": str}]
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()


# ---------------------------------------------------------------------------
# Sidebar — document management
# ---------------------------------------------------------------------------
def render_sidebar():
    st.sidebar.title("🎓 AI Study Buddy")
    st.sidebar.markdown("---")

    # --- Upload new document ---
    st.sidebar.subheader("📄 Upload Document")
    uploaded = st.sidebar.file_uploader(
        "PDF or TXT (max 5 MB)",
        type=["pdf", "txt"],
        help="Upload your notes or syllabus.",
    )
    if uploaded is not None:
        if st.sidebar.button("Process Document", use_container_width=True):
            with st.spinner("Extracting text and chunking topics…"):
                try:
                    record = doc_svc.process_upload(
                        file_bytes=uploaded.read(),
                        filename=uploaded.name,
                        mime_type=uploaded.type or "application/octet-stream",
                    )
                    st.session_state["active_doc"] = record
                    st.session_state["chat_history"] = []
                    st.session_state["quiz_state"] = None
                    st.sidebar.success(
                        f"✅ Loaded **{record['filename']}** — "
                        f"{len(record['topics'])} topic(s) found."
                    )
                except DocumentValidationError as e:
                    st.sidebar.error(str(e))
                except Exception as e:
                    st.sidebar.error(f"Unexpected error: {e}")

    st.sidebar.markdown("---")

    # --- Load previously uploaded document ---
    st.sidebar.subheader("📂 Previous Documents")
    try:
        all_docs = doc_svc.list_documents()
    except Exception:
        all_docs = []

    if all_docs:
        doc_labels = {f"{d['filename']} ({d['uploaded_at'][:10]})": d for d in reversed(all_docs)}
        chosen_label = st.sidebar.selectbox(
            "Select a document", ["— choose —"] + list(doc_labels.keys())
        )
        if chosen_label != "— choose —" and st.sidebar.button("Load Selected", use_container_width=True):
            st.session_state["active_doc"] = doc_labels[chosen_label]
            st.session_state["chat_history"] = []
            st.session_state["quiz_state"] = None
            st.sidebar.success(f"Loaded: {doc_labels[chosen_label]['filename']}")
    else:
        st.sidebar.info("No documents uploaded yet.")

    # Active doc indicator
    active = st.session_state.get("active_doc")
    if active:
        st.sidebar.markdown("---")
        st.sidebar.markdown(f"**Active:** {active['filename']}")
        st.sidebar.markdown(f"Topics: {len(active['topics'])}")


# ---------------------------------------------------------------------------
# Main tabs
# ---------------------------------------------------------------------------
def render_main():
    active = st.session_state.get("active_doc")

    tab_explain, tab_quiz, tab_revision, tab_chat = st.tabs([
        "💡 Explain", "🧠 Quiz", "📅 Revision Plan", "💬 Doubt Chat"
    ])

    with tab_explain:
        render_explain_tab(active)

    with tab_quiz:
        render_quiz_tab(active)

    with tab_revision:
        render_revision_tab(active)

    with tab_chat:
        render_chat_tab(active)


# ---------------------------------------------------------------------------
# Tab: Explain
# ---------------------------------------------------------------------------
def render_explain_tab(active):
    st.header("💡 Explain Like I'm 10")
    if active is None:
        st.info("Upload or select a document from the sidebar to get started.")
        return

    topics = active.get("topics", [])
    if not topics:
        st.warning("No topics found in the document.")
        return

    topic_names = [t["name"] for t in topics]
    selected_name = st.selectbox("Select a topic to explain", topic_names, key="explain_topic")
    selected_topic = next((t for t in topics if t["name"] == selected_name), None)

    if st.button("✨ Explain This Topic", use_container_width=True):
        if selected_topic:
            with st.spinner("Generating explanation…"):
                try:
                    explanation = exp_svc.explain(selected_topic["name"], selected_topic["content"])
                    st.subheader(f"Explanation: {selected_name}")
                    st.markdown(explanation)
                except RuntimeError as e:
                    st.error(f"Could not generate explanation: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")


# ---------------------------------------------------------------------------
# Tab: Quiz
# ---------------------------------------------------------------------------
def render_quiz_tab(active):
    st.header("🧠 Quiz Mode")
    if active is None:
        st.info("Upload or select a document from the sidebar to get started.")
        return

    topics = active.get("topics", [])
    if not topics:
        st.warning("No topics found in the document.")
        return

    quiz_state = st.session_state.get("quiz_state")

    # --- No quiz in progress: show setup ---
    if quiz_state is None:
        topic_names = [t["name"] for t in topics]
        selected_name = st.selectbox("Select a topic for your quiz", topic_names, key="quiz_topic")
        selected_topic = next((t for t in topics if t["name"] == selected_name), None)

        if st.button("🚀 Generate Quiz", use_container_width=True):
            if selected_topic:
                with st.spinner("Generating 5 questions…"):
                    try:
                        quiz = quiz_svc.generate_quiz(
                            selected_topic["name"], selected_topic["content"]
                        )
                        st.session_state["quiz_state"] = {
                            "quiz": quiz,
                            "current_q": 0,
                            "answers": [],
                            "finished": False,
                        }
                        st.rerun()
                    except RuntimeError as e:
                        st.error(f"Could not generate quiz: {e}")
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")
        return

    # --- Quiz in progress ---
    quiz = quiz_state["quiz"]
    questions = quiz["questions"]
    current_q = quiz_state["current_q"]
    answers = quiz_state["answers"]
    finished = quiz_state["finished"]

    # Progress bar
    progress = current_q / len(questions) if not finished else 1.0
    st.progress(progress, text=f"Question {min(current_q + 1, len(questions))} of {len(questions)}")

    if finished:
        _render_quiz_results(quiz_state)
        if st.button("🔄 New Quiz", use_container_width=True):
            st.session_state["quiz_state"] = None
            st.rerun()
        return

    # --- Current question ---
    q = questions[current_q]
    st.subheader(f"Q{current_q + 1}. {q['question']}")

    option_labels = q["options"]
    # Map "A) text" → "A"
    choice = st.radio(
        "Choose your answer:",
        options=[opt[0] for opt in option_labels],  # A, B, C, D
        format_func=lambda letter: next(
            (o for o in option_labels if o.startswith(letter)), letter
        ),
        key=f"quiz_choice_{current_q}",
    )

    if st.button("Submit Answer ➡️", use_container_width=True):
        correct = quiz_svc.check_answer(q, choice)
        answers.append(choice)
        if correct:
            st.success(f"✅ Correct! The answer is **{q['answer']}**.")
        else:
            correct_text = next(
                (o for o in option_labels if o.startswith(q["answer"])), q["answer"]
            )
            st.error(f"❌ Wrong. The correct answer is **{correct_text}**.")

        # Advance
        if current_q + 1 >= len(questions):
            quiz_state["finished"] = True
            score = sum(
                1 for i, a in enumerate(answers)
                if quiz_svc.check_answer(questions[i], a)
            )
            quiz_svc.save_attempt(
                quiz_id=quiz["id"],
                topic=quiz["topic"],
                answers=answers,
                score=score,
                total=len(questions),
            )
        else:
            quiz_state["current_q"] = current_q + 1

        quiz_state["answers"] = answers
        st.session_state["quiz_state"] = quiz_state
        st.rerun()


def _render_quiz_results(quiz_state: dict):
    quiz = quiz_state["quiz"]
    questions = quiz["questions"]
    answers = quiz_state["answers"]
    score = sum(
        1 for i, a in enumerate(answers)
        if i < len(questions) and quiz_svc.check_answer(questions[i], a)
    )
    total = len(questions)
    pct = int(score / total * 100) if total else 0

    st.subheader("🎉 Quiz Complete!")
    col1, col2 = st.columns(2)
    col1.metric("Score", f"{score} / {total}")
    col2.metric("Percentage", f"{pct}%")

    if pct >= 80:
        st.success("Excellent work! 🏆")
    elif pct >= 50:
        st.warning("Good effort! Keep revising. 📚")
    else:
        st.error("Keep studying — you'll get there! 💪")

    with st.expander("Review all answers"):
        for i, q in enumerate(questions):
            user_ans = answers[i] if i < len(answers) else "–"
            correct = quiz_svc.check_answer(q, user_ans)
            icon = "✅" if correct else "❌"
            correct_option = next(
                (o for o in q["options"] if o.startswith(q["answer"])), q["answer"]
            )
            st.markdown(
                f"**Q{i+1}.** {q['question']}  \n"
                f"{icon} Your answer: **{user_ans}** | Correct: **{correct_option}**"
            )


# ---------------------------------------------------------------------------
# Tab: Revision Plan
# ---------------------------------------------------------------------------
def render_revision_tab(active):
    st.header("📅 Revision Plan Generator")
    if active is None:
        st.info("Upload or select a document from the sidebar to get started.")
        return

    topics = active.get("topics", [])
    if not topics:
        st.warning("No topics found in the document.")
        return

    topic_names = [t["name"] for t in topics]

    col1, col2 = st.columns([1, 2])
    with col1:
        min_date = datetime.date.today() + datetime.timedelta(days=1)
        exam_date = st.date_input(
            "Exam Date",
            value=min_date,
            min_value=min_date,
            key="rev_exam_date",
        )
    with col2:
        selected_topics = st.multiselect(
            "Topics to revise",
            topic_names,
            default=topic_names,
            key="rev_topics",
        )

    if st.button("📋 Generate Revision Plan", use_container_width=True):
        if not selected_topics:
            st.error("Please select at least one topic.")
        else:
            with st.spinner("Building your revision plan…"):
                try:
                    plan = rev_svc.generate_plan(
                        exam_date=exam_date,
                        topics=selected_topics,
                        document_title=active.get("filename", ""),
                    )
                    st.subheader(f"Your Revision Plan — Exam on {exam_date}")
                    st.markdown(plan["plan_text"])
                except RevisionValidationError as e:
                    st.error(str(e))
                except RuntimeError as e:
                    st.error(f"Could not generate plan: {e}")
                except Exception as e:
                    st.error(f"Unexpected error: {e}")

    # Show past plans
    with st.expander("📜 Past Revision Plans"):
        try:
            past = rev_svc.list_plans()
        except Exception:
            past = []
        if past:
            for p in reversed(past[-5:]):
                st.markdown(f"**{p.get('document_title', 'Document')}** — Exam: {p['exam_date']} (created {p['created_at'][:10]})")
                st.markdown(p["plan_text"])
                st.markdown("---")
        else:
            st.info("No revision plans generated yet.")


# ---------------------------------------------------------------------------
# Tab: Doubt Chat
# ---------------------------------------------------------------------------
def render_chat_tab(active):
    st.header("💬 Doubt-Solving Chat")
    if active is None:
        st.info("Upload or select a document from the sidebar to get started.")
        return

    topics = active.get("topics", [])

    # Render chat history
    chat_history: list[dict] = st.session_state.get("chat_history", [])
    for msg in chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Input
    query = st.chat_input("Ask a question about your document…")
    if query:
        # Display user message
        with st.chat_message("user"):
            st.markdown(query)
        chat_history.append({"role": "user", "content": query})

        # Get answer
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    answer = chat_svc.answer(
                        query=query,
                        topics=topics,
                        chat_history=chat_history[:-1],  # exclude current turn
                    )
                    st.markdown(answer)
                    chat_history.append({"role": "assistant", "content": answer})
                except ChatValidationError as e:
                    msg = str(e)
                    st.error(msg)
                    chat_history.append({"role": "assistant", "content": f"⚠️ {msg}"})
                except RuntimeError as e:
                    msg = f"Could not get an answer: {e}"
                    st.error(msg)
                    chat_history.append({"role": "assistant", "content": f"⚠️ {msg}"})
                except Exception as e:
                    msg = f"Unexpected error: {e}"
                    st.error(msg)
                    chat_history.append({"role": "assistant", "content": f"⚠️ {msg}"})

        st.session_state["chat_history"] = chat_history

    if chat_history and st.button("🗑️ Clear Chat", key="clear_chat"):
        st.session_state["chat_history"] = []
        st.rerun()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
render_sidebar()
render_main()
