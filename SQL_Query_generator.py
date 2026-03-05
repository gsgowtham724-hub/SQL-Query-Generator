# ============================
# MODEL PIPELINE
# ============================
from transformers import pipeline

pipe = pipeline("text-generation", model="ibm-granite/granite-3.3-2b-instruct")

messages = [{"role": "user", "content": "Who are you?"}]
pipe(messages)

# ============================
# IMPORTS
# ============================
import gradio as gr
from datetime import datetime
from pathlib import Path
import json
import sqlite3
import re
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import urllib.parse

# ============================
# GLOBAL HISTORY
# ============================
query_history = []

# ============================
# DATABASE SCHEMA
# ============================
SCHEMA = {
    "users": {
        "id": "INTEGER PRIMARY KEY",
        "name": "TEXT",
        "email": "TEXT",
        "signup_date": "DATE",
        "age": "INTEGER",
        "country": "TEXT",
        "status": "TEXT",
    },
    "orders": {
        "id": "INTEGER PRIMARY KEY",
        "user_id": "INTEGER",
        "product_name": "TEXT",
        "amount": "REAL",
        "order_date": "DATE",
        "status": "TEXT",
    },
    "products": {
        "id": "INTEGER PRIMARY KEY",
        "name": "TEXT",
        "price": "REAL",
        "category": "TEXT",
        "stock": "INTEGER",
    },
    "transactions": {
        "id": "INTEGER PRIMARY KEY",
        "user_id": "INTEGER",
        "amount": "REAL",
        "date": "DATE",
        "type": "TEXT",
    },
}

# ============================
# SECURITY
# ============================
DANGEROUS_KEYWORDS = ["DROP", "DELETE", "ALTER", "TRUNCATE", "INSERT", "UPDATE", "EXEC"]
DANGEROUS_CHARS = [";", "--", "xp_", "sp_"]


def is_safe(text):
    text_upper = text.upper()
    for k in DANGEROUS_KEYWORDS:
        if k in text_upper:
            return False
    for c in DANGEROUS_CHARS:
        if c in text:
            return False
    return True


# ============================
# TABLE DETECTION
# ============================
def get_table_name(query_text):
    query_lower = query_text.lower()

    keyword_map = {
        "users": ["user", "customer", "account", "profile"],
        "orders": ["order", "purchase", "buy"],
        "products": ["product", "item", "goods"],
        "transactions": ["transaction", "payment", "transfer"],
    }

    for table, words in keyword_map.items():
        for w in words:
            if w in query_lower:
                return table

    return "users"


# ============================
# COLUMN DETECTION
# ============================
def get_column_names(table_name, query_text):
    query_lower = query_text.lower()
    columns = list(SCHEMA[table_name].keys())
    selected = []

    column_map = {
        "name": ["name"],
        "email": ["email"],
        "signup_date": ["signup", "joined", "registered"],
        "age": ["age"],
        "amount": ["amount", "price", "cost"],
        "status": ["status"],
        "country": ["country"],
    }

    for col, keys in column_map.items():
        if col in columns:
            for k in keys:
                if k in query_lower:
                    selected.append(col)
                    break

    if not selected:
        return ["*"]

    return list(dict.fromkeys(selected))


# ============================
# CONDITIONS
# ============================
def extract_conditions(query_text):

    q = query_text.lower()
    conditions = []

    if "last month" in q:
        conditions.append("DATE(signup_date) >= DATE('now','-1 month')")

    if "last week" in q:
        conditions.append("DATE(signup_date) >= DATE('now','-7 days')")

    if "today" in q:
        conditions.append("DATE(signup_date) = DATE('now')")

    if "active" in q:
        conditions.append("status='active'")

    if "inactive" in q:
        conditions.append("status='inactive'")

    more = re.search(r"(more than|above)\s+(\d+)", q)
    if more:
        conditions.append(f"amount > {more.group(2)}")

    less = re.search(r"(less than|below)\s+(\d+)", q)
    if less:
        conditions.append(f"amount < {less.group(2)}")

    return conditions


# ============================
# SQL GENERATION
# ============================
def generate_sql(query_text):

    if not is_safe(query_text):
        return None, "❌ Unsafe query"

    table = get_table_name(query_text)
    cols = get_column_names(table, query_text)

    col_str = "*" if cols == ["*"] else ", ".join(cols)

    sql = f"SELECT {col_str} FROM {table}"

    conditions = extract_conditions(query_text)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    if "all" not in query_text.lower():
        sql += " LIMIT 10"

    return sql, f"Generated from table {table}"


# ============================
# PROCESS QUERY
# ============================
def process_query(user_query, history):

    if not user_query.strip():
        return history

    sql, exp = generate_sql(user_query)

    if sql is None:
        response = exp
    else:
        response = f"```sql\n{sql}\n```\n\n{exp}"

    query_history.append(
        {"user": user_query, "sql": sql, "timestamp": datetime.now().isoformat()}
    )

    history.append((user_query, response))
    return history


# ============================
# CLEAR CHAT
# ============================
def clear_chat():
    global query_history
    query_history = []
    return []


# ============================
# PDF EXPORT
# ============================
def download_pdf():

    if not query_history:
        return "No queries", None

    filename = f"queries_{datetime.now().strftime('%H%M%S')}.pdf"

    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()

    story = []
    story.append(Paragraph("SQL Query Report", styles["Heading1"]))
    story.append(Spacer(1, 20))

    for q in query_history:
        story.append(Paragraph(f"User: {q['user']}", styles["Normal"]))
        story.append(Paragraph(f"SQL: {q['sql']}", styles["Code"]))
        story.append(Spacer(1, 10))

    doc.build(story)

    return "PDF Created", filename


# ============================
# TXT EXPORT
# ============================
def download_txt():

    if not query_history:
        return "No queries", None

    text = ""

    for q in query_history:
        text += f"{q['user']}\n{q['sql']}\n\n"

    filename = f"queries_{datetime.now().strftime('%H%M%S')}.txt"
    Path(filename).write_text(text)

    return "TXT Created", filename


# ============================
# SHARE LINKS
# ============================
def generate_whatsapp_link():

    if not query_history:
        return "No queries"

    msg = "SQL Queries:\n"

    for q in query_history[-5:]:
        msg += f"{q['user']} -> {q['sql']}\n"

    link = "https://wa.me/?text=" + urllib.parse.quote(msg)

    return f"[Click to Share WhatsApp]({link})"


# ============================
# GRADIO UI
# ============================
with gr.Blocks(title="SQL Generator") as demo:

    gr.Markdown("# SQL Query Generator")

    chatbot = gr.Chatbot(height=400)

    with gr.Row():
        query_input = gr.Textbox(label="Enter request")
        send_btn = gr.Button("Generate")

    send_btn.click(process_query, [query_input, chatbot], chatbot)
    query_input.submit(process_query, [query_input, chatbot], chatbot)

    clear_btn = gr.Button("Clear")
    clear_btn.click(clear_chat, None, chatbot)

    pdf_btn = gr.Button("Download PDF")
    txt_btn = gr.Button("Download TXT")

    pdf_file = gr.File()
    txt_file = gr.File()

    pdf_btn.click(download_pdf, None, pdf_file)
    txt_btn.click(download_txt, None, txt_file)

    share = gr.Markdown()

    share_btn = gr.Button("Share WhatsApp")
    share_btn.click(generate_whatsapp_link, None, share)

demo.launch(share=True)