"""AWS AIF Pal, adapted from the local browser app for Streamlit."""

from __future__ import annotations

import html
import json
import math
import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from core import (
    DOMAINS,
    correct_count,
    finish_session,
    is_correct,
    load_bank,
    merge_attempts,
    new_session,
    score,
    valid_attempt,
    valid_session,
)


APP_DIR = Path(__file__).parent
SESSION_KEY = "aif-pal-streamlit-session-v1"
HISTORY_KEY = "aif-pal-streamlit-attempts-v1"

# A small native Streamlit component reads and writes this visitor's localStorage.
# It avoids relying on Community Cloud's temporary server filesystem for history.
STORAGE_JS = r"""
export default function({data, setStateValue}) {
  const sessionKey = 'aif-pal-streamlit-session-v1';
  const historyKey = 'aif-pal-streamlit-attempts-v1';
  if (data.action === 'read') {
    let snapshot;
    try {
      const session = JSON.parse(localStorage.getItem(sessionKey) || 'null');
      const attempts = JSON.parse(localStorage.getItem(historyKey) || '[]');
      snapshot = {session, attempts, error: null};
    } catch (error) {
      snapshot = {session: null, attempts: [], error: String(error)};
    }
    setStateValue('snapshot', snapshot);
  } else if (data.action === 'write') {
    try {
      if (data.session === null) localStorage.removeItem(sessionKey);
      else localStorage.setItem(sessionKey, JSON.stringify(data.session));
      localStorage.setItem(historyKey, JSON.stringify(data.attempts));
    } catch (error) {
      setStateValue('storage_error', String(error));
    }
  }
}
"""

st.set_page_config(page_title="AWS AIF Pal · AIF-C01 practice", page_icon="✦", layout="wide")
st.markdown(f"<style>{(APP_DIR / 'style.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
storage_component = st.components.v2.component("aif_pal_browser_storage", js=STORAGE_JS)


@st.cache_data(show_spinner=False)
def bank_data() -> list[dict]:
    return load_bank()


BANK = bank_data()
BY_ID = {question["id"]: question for question in BANK}


def mark_changed() -> None:
    st.session_state.sync_revision += 1


def hydrate_storage() -> None:
    if "hydrated" not in st.session_state:
        st.session_state.hydrated = False
        st.session_state.sync_revision = 0
        st.session_state.view = "setup"
        st.session_state.return_view = "setup"
        st.session_state.session = None
        st.session_state.attempts = []

    if not st.session_state.hydrated:
        result = storage_component(
            key="pal-storage",
            data={"action": "read"},
            on_snapshot_change=lambda: None,
            on_storage_error_change=lambda: None,
        )
        snapshot = result.snapshot
        if snapshot is None:
            st.caption("Loading saved practice history…")
            st.stop()
        session = snapshot.get("session") if isinstance(snapshot, dict) else None
        attempts = snapshot.get("attempts", []) if isinstance(snapshot, dict) else []
        st.session_state.session = session if valid_session(session, BY_ID) else None
        st.session_state.attempts = [row for row in attempts if valid_attempt(row)] if isinstance(attempts, list) else []
        st.session_state.hydrated = True
        if st.session_state.session:
            if st.session_state.session.get("completedAt"):
                row = finish_session(st.session_state.session, BY_ID)
                st.session_state.attempts = merge_attempts(st.session_state.attempts, row)
                st.session_state.view = "results"
            else:
                st.session_state.view = "question"
        if snapshot.get("error"):
            st.warning("Browser storage is unavailable. Attempts may not remain after this tab closes.")
        st.rerun()

    result = storage_component(
        key="pal-storage",
        data={
            "action": "write" if st.session_state.sync_revision else "idle",
            "revision": st.session_state.sync_revision,
            "session": st.session_state.session,
            "attempts": st.session_state.attempts,
        },
        on_snapshot_change=lambda: None,
        on_storage_error_change=lambda: None,
    )
    if result.storage_error:
        st.warning("Browser storage is unavailable. Attempts may not remain after this tab closes.")


def finish_active() -> None:
    session = st.session_state.session
    if not session or session.get("completedAt"):
        return
    row = finish_session(session, BY_ID)
    st.session_state.attempts = merge_attempts(st.session_state.attempts, row)
    st.session_state.view = "results"
    mark_changed()


def remaining_seconds(session: dict) -> int:
    return max(0, math.ceil((session["endsAt"] - time.time() * 1000) / 1000))


def elapsed_text(milliseconds: float) -> str:
    seconds = int(milliseconds // 1000)
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


def go(view: str) -> None:
    st.session_state.view = view
    st.rerun()


def answer_changed(question_id: str, widget_key: str, multiple: bool) -> None:
    selected = st.session_state[widget_key]
    response = list(selected) if multiple else ([] if selected is None else [selected])
    session = st.session_state.session
    session["responses"][question_id] = response
    session["checked"].pop(question_id, None)
    mark_changed()


def topbar() -> None:
    col_brand, col_note = st.columns([1, 1], vertical_alignment="center")
    with col_brand:
        st.markdown('<div class="pal-brand"><span class="pal-mark">✦</span> AWS AIF <b>Pal</b></div>', unsafe_allow_html=True)
    with col_note:
        st.markdown('<span class="top-note">AI PRACTITIONER · AIF-C01</span>', unsafe_allow_html=True)


def bottom_navigation() -> None:
    st.divider()
    left, right = st.columns(2)
    with left:
        if st.session_state.view == "history":
            if st.button("← Back", key="bottom-back", width="stretch"):
                go(st.session_state.return_view)
        elif st.button("History", key="bottom-history", width="stretch"):
            st.session_state.return_view = st.session_state.view
            go("history")
    with right:
        if st.session_state.session and st.button("New session", key="bottom-new", width="stretch"):
            go("setup")


@st.fragment(run_every="1s")
def timer_fragment() -> None:
    session = st.session_state.session
    if not session or session.get("completedAt"):
        return
    remaining = remaining_seconds(session)
    if remaining == 0:
        finish_active()
        st.rerun()
    css = "urgent" if remaining <= 300 else "warning" if remaining <= 600 else ""
    st.markdown(f'<div class="pal-timer {css}">◷ &nbsp; {elapsed_text(remaining * 1000)}</div>', unsafe_allow_html=True)
    if remaining <= 300:
        st.caption("5 minutes or less remaining")
    elif remaining <= 600:
        st.caption("10 minutes or less remaining")


def setup_page() -> None:
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.markdown(
            '<div class="hero-copy"><p class="eyebrow">— &nbsp; YOUR AIF-C01 STUDY COMPANION</p>'
            '<h1>Practice with<br><em>purpose.</em></h1>'
            '<p>Build service intuition with realistic scenarios, focused explanations, and a question bank that follows the current AI Practitioner domains.</p>'
            '<div class="hero-stats"><div><strong>512</strong><span>questions</span></div>'
            '<div><strong>400</strong><span>original items</span></div>'
            '<div><strong>5</strong><span>exam domains</span></div></div>'
            '<p class="source-note">Includes 102 Taulli study guide questions and 10 supplied examples.</p></div>',
            unsafe_allow_html=True,
        )
    with right:
        st.markdown('<p class="overline">01 &nbsp; SET UP YOUR SESSION</p><h2 class="section-title">Make it yours</h2>', unsafe_allow_html=True)
        session = st.session_state.session
        if session and not session.get("completedAt") and st.button("↗  Resume session", width="stretch"):
            go("question")
        with st.form("setup-form"):
            mode = st.radio("Choose a mode", ["exam", "guide"], format_func=lambda x: "◷  Exam mode — score at the end" if x == "exam" else "✧  Guide mode — check each answer")
            count = st.number_input("Questions", min_value=1, max_value=len(BANK), value=65, step=1)
            minutes = st.number_input("Time limit (minutes)", min_value=1, max_value=600, value=90, step=1)
            source = st.selectbox("Question pool", ["all", "original", "book", "provided"], format_func=lambda x: {
                "all": "All questions (512)", "original": "Original practice (400)",
                "book": "Taulli study guide (102)", "provided": "Your 10 examples (10)",
            }[x])
            submitted = st.form_submit_button("Start practice  →", type="primary", width="stretch")
        if submitted:
            st.session_state.session = new_session(BANK, source, mode, min(count, sum(q["origin"] == source for q in BANK) if source != "all" else len(BANK)), minutes)
            st.session_state.view = "question"
            mark_changed()
            st.rerun()
        st.caption("Random questions and option order every session · Progress saves in this browser")
    st.markdown(
        '<div class="feature-row"><div><b>◎ &nbsp; Exam focus</b><p>Practice service selection, model concepts, responsible AI, and security.</p></div>'
        '<div><b>◇ &nbsp; Learn from misses</b><p>Review wrong answers with explanations and source links.</p></div>'
        '<div><b>◷ &nbsp; Stay on pace</b><p>See timer warnings at 10 and 5 minutes remaining.</p></div></div>',
        unsafe_allow_html=True,
    )


def session_header() -> None:
    session = st.session_state.session
    answered = sum(bool(session["responses"].get(item["id"])) for item in session["items"])
    title, timer = st.columns([3, 1], vertical_alignment="center")
    with title:
        st.markdown(f'<p class="overline">{html.escape(session["mode"].upper())} MODE</p><h1 class="page-title">{"Check answers" if st.session_state.view == "review" else "Your practice session"}</h1>', unsafe_allow_html=True)
    with timer:
        timer_fragment()
    st.caption(f"{answered} of {len(session['items'])} answered")
    st.progress(answered / len(session["items"]))


def question_page() -> None:
    session = st.session_state.session
    session_header()
    item = session["items"][session["current"]]
    question = BY_ID[item["id"]]
    response = session["responses"].get(question["id"], [])
    st.markdown(f'<span class="pill">QUESTION {session["current"] + 1:02d} / {len(session["items"])}</span> &nbsp; <span class="domain-label">DOMAIN {question["domain"]} · {html.escape(DOMAINS[question["domain"]])}</span>', unsafe_allow_html=True)
    st.markdown(f'<p class="question-type">{"SELECT " + str(len(question["answer"])) + " ANSWERS" if question["type"] == "multiple" else "SELECT ONE ANSWER"} &nbsp; · &nbsp; {html.escape(question["source"])}</p>', unsafe_allow_html=True)
    st.markdown(f'<h2 class="question-title">{html.escape(question["prompt"])}</h2>', unsafe_allow_html=True)
    key = f"answer-{session['startedAt']}-{question['id']}"
    labels = {index: f"{chr(65 + visual)}.  {question['options'][index]}" for visual, index in enumerate(item["order"])}
    if key not in st.session_state:
        st.session_state[key] = response if question["type"] == "multiple" else (response[0] if response else None)
    if question["type"] == "multiple":
        st.multiselect("Select answers", item["order"], format_func=lambda value: labels[value], key=key,
                       on_change=answer_changed, args=(question["id"], key, True))
    else:
        st.radio("Answer", item["order"], format_func=lambda value: labels[value], key=key,
                 on_change=answer_changed, args=(question["id"], key, False))
    response = session["responses"].get(question["id"], [])
    if session["mode"] == "guide":
        if st.button("Check answer  ✓", disabled=len(response) != len(question["answer"]), type="secondary"):
            session["checked"][question["id"]] = True
            mark_changed()
            st.rerun()
        if session["checked"].get(question["id"]):
            correct_text = "; ".join(question["options"][index] for index in question["answer"])
            if is_correct(question, response):
                st.success("Correct answer")
            else:
                st.error("Not quite")
            st.markdown(f"**Correct:** {correct_text}")
            st.write(question["explanation"])
            if question.get("reference", "").startswith("https://"):
                st.link_button("Open source ↗", question["reference"])
    st.divider()
    previous, review, next_button = st.columns(3)
    with previous:
        if st.button("← Previous", disabled=session["current"] == 0, width="stretch"):
            session["current"] -= 1
            mark_changed()
            st.rerun()
    with review:
        if st.button("Check answers", width="stretch"):
            go("review")
    with next_button:
        last = session["current"] == len(session["items"]) - 1
        if st.button("Finish session →" if last else "Next question →", type="primary", width="stretch"):
            if last:
                finish_active()
            else:
                session["current"] += 1
                mark_changed()
            st.rerun()


def review_page() -> None:
    session = st.session_state.session
    session_header()
    answered = sum(bool(session["responses"].get(item["id"])) for item in session["items"])
    st.subheader("Choose where to go next.")
    st.caption(f"{answered} answered · {len(session['items']) - answered} unanswered. You can change any selection before finishing.")
    if st.button("Finish session →", type="primary"):
        finish_active()
        st.rerun()
    choices = list(range(len(session["items"])))
    selected = st.selectbox("Jump to question", choices, index=session["current"], format_func=lambda i: f"{i + 1:02d} · D{BY_ID[session['items'][i]['id']]['domain']} · {'✓ Answered' if session['responses'].get(session['items'][i]['id']) else '○ Unanswered'}")
    if st.button("Go to question", width="stretch"):
        session["current"] = selected
        mark_changed()
        go("question")
    with st.expander("All question statuses", expanded=True):
        for start in range(0, len(choices), 5):
            columns = st.columns(min(5, len(choices) - start))
            for column, index in zip(columns, choices[start:start + 5]):
                item = session["items"][index]
                symbol = "✓" if session["responses"].get(item["id"]) else "○"
                with column:
                    if st.button(f"{index + 1:02d} {symbol}", key=f"jump-{index}", width="stretch"):
                        session["current"] = index
                        mark_changed()
                        go("question")


def results_page() -> None:
    session = st.session_state.session
    total = len(session["items"])
    correct = correct_count(session, BY_ID)
    raw_score = score(session, BY_ID)
    display_score = str(int(raw_score)) if raw_score.is_integer() else f"{raw_score:.1f}"
    st.markdown(f'<p class="overline center">SESSION COMPLETE</p><h1 class="page-title center">{"Time is up." if session["finishReason"] == "time" else "Good work. Keep going."}</h1>', unsafe_allow_html=True)
    st.markdown('<p class="center muted">Your practice result and corrections are ready below.</p>', unsafe_allow_html=True)
    left, right = st.columns([1.05, .95], gap="medium")
    with left:
        st.markdown(f'<div class="score-card"><span>YOUR PRACTICE SCORE</span><strong>{display_score}<small> / 1000</small></strong><div class="score-details"><div>{correct} correct</div><div>{total-correct} missed</div><div>{round(correct/total*100)}% accuracy</div></div><p>Each correct answer is worth exactly 1000 ÷ {total} points (about {1000/total:.2f}). Unanswered questions earn 0. This practice score is separate from AWS scaled exam scoring.</p></div>', unsafe_allow_html=True)
    with right:
        st.markdown('<p class="overline">PERFORMANCE BY DOMAIN</p>', unsafe_allow_html=True)
        for domain, name in DOMAINS.items():
            items = [item for item in session["items"] if BY_ID[item["id"]]["domain"] == domain]
            good = sum(is_correct(BY_ID[item["id"]], session["responses"].get(item["id"])) for item in items)
            st.caption(f"D{domain} · {name}: {good}/{len(items)}")
            st.progress(good / len(items) if items else 0)
    st.markdown('<p class="overline results-overline">REVIEW YOUR MISSES</p>', unsafe_allow_html=True)
    missed = [(i, BY_ID[item["id"]]) for i, item in enumerate(session["items"]) if not is_correct(BY_ID[item["id"]], session["responses"].get(item["id"]))]
    st.subheader(f"{len(missed)} questions to revisit" if missed else "Every answer was correct")
    for index, question in missed:
        response = session["responses"].get(question["id"], [])
        your_answer = "; ".join(question["options"][choice] for choice in response) if response else "No answer"
        right_answer = "; ".join(question["options"][choice] for choice in question["answer"])
        with st.expander(f"Question {index + 1} · {question['prompt']}"):
            st.write(f"**Your answer:** {your_answer}")
            st.write(f"**Correct answer:** {right_answer}")
            st.write(question["explanation"])
            st.caption(question["source"])
            if question.get("reference", "").startswith("https://"):
                st.link_button("Open source ↗", question["reference"])


def history_page() -> None:
    attempts = sorted(st.session_state.attempts, key=lambda row: row["completedAt"], reverse=True)
    st.markdown('<p class="overline">YOUR PROGRESS</p><h1 class="page-title">Attempt history</h1><p class="muted">Completed exam and guide sessions are saved in this browser.</p>', unsafe_allow_html=True)
    st.markdown('<p class="overline history-overline">PERFORMANCE OVER TIME</p><h2 class="section-title">Your trend</h2>', unsafe_allow_html=True)
    a, b = st.columns(2)
    with a:
        metric = st.selectbox("Measure", ["Score %", "Score / 1000", "Elapsed minutes", "Question count", "Correct answers"])
        mode = st.selectbox("Mode", ["All modes", "Exam", "Guide"])
    with b:
        chart_type = st.selectbox("Chart type", ["Line", "Bar"])
        range_label = st.selectbox("Attempts shown", ["Last 10", "Last 25", "All"])
    filtered = [row for row in attempts if mode == "All modes" or row["mode"] == mode.lower()]
    filtered = list(reversed(filtered[:{"Last 10": 10, "Last 25": 25, "All": len(filtered)}[range_label]]))
    if filtered:
        measures = {
            "Score %": lambda r: r["correct"] * 100 / r["questions"],
            "Score / 1000": lambda r: r["correct"] * 1000 / r["questions"],
            "Elapsed minutes": lambda r: r["elapsedMs"] / 60_000,
            "Question count": lambda r: r["questions"],
            "Correct answers": lambda r: r["correct"],
        }
        chart_data = [{"Date": datetime.fromtimestamp(row["completedAt"] / 1000).isoformat(), metric: round(measures[metric](row), 2), "Mode": row["mode"].capitalize()} for row in filtered]
        chart = {
            "data": {"values": chart_data},
            "mark": {"type": "line" if chart_type == "Line" else "bar", "point": True if chart_type == "Line" else False, "color": "#3e8f80", "tooltip": True},
            "encoding": {
                "x": {"field": "Date", "type": "temporal", "title": "Completed at"},
                "y": {"field": metric, "type": "quantitative", "title": metric, "scale": {"zero": True}},
                "tooltip": [{"field": "Date", "type": "temporal"}, {"field": metric, "type": "quantitative"}, {"field": "Mode", "type": "nominal"}],
            },
            "height": 300,
        }
        st.vega_lite_chart(chart, width="stretch", alt=f"{metric} over completion time for {len(filtered)} attempts")
        st.caption(f"{len(filtered)} completed {'attempt' if len(filtered) == 1 else 'attempts'} · exact values are in the table")
    else:
        st.info("No completed sessions match these graph settings.")
    st.markdown('<p class="overline history-overline">ALL COMPLETED ATTEMPTS</p><h2 class="section-title">Session log</h2>', unsafe_allow_html=True)
    if attempts:
        rows = []
        for row in attempts:
            values = [
                datetime.fromtimestamp(row["completedAt"] / 1000).strftime("%b %d, %Y · %I:%M %p"),
                row["mode"].capitalize(), str(row["questions"]), elapsed_text(row["elapsedMs"]),
                f"{row['correct'] * 1000 / row['questions']:.1f} / 1000",
                f"{row['correct'] * 100 / row['questions']:.1f}%",
            ]
            rows.append("<tr>" + "".join(f'<td data-label="{label}">{html.escape(value)}</td>' for label, value in zip(["Date", "Mode", "Questions", "Elapsed", "Score", "Score %"], values)) + "</tr>")
        st.markdown('<div class="history-table-wrap"><table class="history-table"><thead><tr><th>Date</th><th>Mode</th><th>Questions</th><th>Elapsed</th><th>Score</th><th>Score %</th></tr></thead><tbody>' + "".join(rows) + '</tbody></table></div>', unsafe_allow_html=True)
    else:
        st.info("Complete a session to start your history.")
    st.caption("History is stored in this browser on this device. Clearing its site data removes it.")
    st.download_button("Download history JSON", json.dumps(attempts, ensure_ascii=False, indent=2), file_name="aif-pal-history.json", mime="application/json")


hydrate_storage()
session = st.session_state.session
if session and not session.get("completedAt") and remaining_seconds(session) == 0:
    finish_active()
topbar()
st.divider()
view = st.session_state.view
if view == "history":
    history_page()
elif view == "setup" or session is None:
    setup_page()
elif view == "review" and not session.get("completedAt"):
    review_page()
elif view == "results" or session.get("completedAt"):
    results_page()
else:
    question_page()
bottom_navigation()
st.divider()
st.caption("Independent practice tool · Based on the AWS AIF-C01 exam guide")
