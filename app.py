from dotenv import load_dotenv
load_dotenv()    # reads the .env file into os.environ

from flask import Flask, render_template, request, redirect, url_for
from google import genai
import sqlite3
from datetime import datetime
import os
import uuid

# PDF generation using ReportLab
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

# Image generation using Pillow
from PIL import Image, ImageDraw, ImageFont

load_dotenv()
key = os.getenv('AIzaSyBvmQh8Y‑WY_d_5nwvO49WkrYEreCrjmRQ')

# --- Database setup for ratings and history ---
DB_PATH = 'excuses.db'
PROOF_DIR = os.path.join('static', 'proofs')
os.makedirs(PROOF_DIR, exist_ok=True)

# Initialize SQLite DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS excuses (
            id INTEGER PRIMARY KEY,
            text TEXT UNIQUE,
            rating INTEGER,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

app = Flask("excuse")

SCENARIOS = ['School', 'Office', 'Family', 'Friends', 'Social Event', 'Late']
CRITICALITY = ['Low', 'Medium', 'High']

# --- DB helper functions ---
def save_excuse_to_db(text):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute('INSERT OR IGNORE INTO excuses(text, rating, created_at) VALUES (?, NULL, ?)', (text, now))
    conn.commit()
    cur.execute('SELECT id FROM excuses WHERE text = ?', (text,))
    exc_id = cur.fetchone()[0]
    conn.close()
    return exc_id

def rate_excuse_in_db(excuse_id, rating):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('UPDATE excuses SET rating = ? WHERE id = ?', (rating, excuse_id))
    conn.commit()
    conn.close()

def list_excuses(limit=10):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute('SELECT id, text, rating, created_at FROM excuses ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    formatted = []
    for row in rows:
        dt = datetime.fromisoformat(row[3])
        human_time = dt.strftime('%b %d, %Y – %I:%M %p')
        formatted.append((row[0], row[1], row[2], human_time))
    return formatted

# --- AI excuse generation ---
def generate_excuse(scenario, criticality, with_proof=False, proof_type=None):
    base_prompt = (
        f"Write one clear, natural-sounding excuse in 10–25 words for this situation. "
        f"Do NOT include bullet points, labels, or promises like 'I'll explain when'. "
        f"Keep it realistic and context-appropriate.\n"
        f"Scenario: {scenario}. Urgency: {criticality}."
    )

    if with_proof and proof_type in ['medical', 'document']:
        base_prompt += " The excuse must involve a health issue (e.g., illness, medical emergency, injury)."

    client = genai.Client(api_key="AIzaSyBvmQh8Y-WY_d_5nwvO49WkrYEreCrjmRQ")
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[base_prompt]
    )
    excuse = response.text.strip().split('\n')[0]
    exc_id = save_excuse_to_db(excuse)
    return exc_id, excuse

# --- Enhanced Proof generation ---
def generate_pdf_proof(excuse_text, proof_type):
    import re

    # Simple mapping of health excuses to diagnoses
    def map_excuse_to_diagnosis(excuse):
        excuse = excuse.lower()
        if "headache" in excuse:
            return "Patient reports acute migraine symptoms requiring rest."
        elif "stomach" in excuse or "food" in excuse:
            return "Patient experiencing gastroenteritis symptoms after suspected food reaction."
        elif "cold" in excuse or "flu" in excuse:
            return "Symptoms consistent with viral upper respiratory infection (common cold)."
        elif "nurse" in excuse or "allergic" in excuse:
            return "Possible allergic reaction observed. Antihistamines recommended."
        elif "fever" in excuse:
            return "Fever reported. Advised to rest and monitor for escalation."
        elif "clinic" in excuse or "medical" in excuse:
            return "Attended urgent care clinic for health concerns. Follow-up required."
        elif "vomit" in excuse or "nausea" in excuse:
            return "Acute nausea and vomiting symptoms. Advised rest and hydration."
        else:
            return "Patient required medical attention for unspecified minor illness."

    # Determine diagnosis based on excuse
    diagnosis = map_excuse_to_diagnosis(excuse_text)

    filename = f"proof_{uuid.uuid4().hex}.pdf"
    path = os.path.join(PROOF_DIR, filename)
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter

    # Header
    c.setFillColor(colors.darkblue)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, height - 50, "Sunrise Medical Center")
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 65, "123 Health Ave, Wellness City, Care State")
    c.line(50, height - 70, width - 50, height - 70)

    # Title
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 100, f"{proof_type.capitalize()} Report")

    # Table with diagnosis instead of original excuse
    styles = getSampleStyleSheet()
    data = [
        [Paragraph('<b>Date</b>', styles['Normal']), datetime.utcnow().strftime('%Y-%m-%d')],
        [Paragraph('<b>Patient</b>', styles['Normal']), 'John Doe'],
        [Paragraph('<b>Details</b>', styles['Normal']), diagnosis]
    ]
    table = Table(data, colWidths=[100, width - 150])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP')
    ]))
    table.wrapOn(c, width, height)
    table.drawOn(c, 50, height - 250)

    # Doctor signature line
    c.line(50, height - 300, 200, height - 300)
    c.setFont("Helvetica", 10)
    c.drawString(50, height - 315, "Dr. Emily Smith, MD")

    c.showPage()
    c.save()
    return '/' + path


def generate_image_proof(excuse_text, proof_type):
    filename = f"proof_{uuid.uuid4().hex}.png"
    path = os.path.join(PROOF_DIR, filename)
    img = Image.new('RGB', (500, 300), 'white')
    draw = ImageDraw.Draw(img)

    # Header bar
    draw.rectangle([0, 0, 500, 40], fill=(30,144,255))
    draw.text((10, 10), f"{proof_type.capitalize()} Proof", font=ImageFont.load_default(), fill='white')

    # Border
    draw.rectangle([5, 5, 495, 295], outline='black', width=2)

    # Excuse text
    draw.multiline_text((20, 60), excuse_text, font=ImageFont.load_default(), spacing=4)

    img.save(path)
    return '/' + path

# --- Dispatcher ---
def generate_proof_file(excuse_text, proof_type):
    if proof_type in ['medical', 'document']:
        return generate_pdf_proof(excuse_text, proof_type)
    else:
        return generate_image_proof(excuse_text, proof_type)

# --- Flask routes ---
@app.route('/', methods=['GET', 'POST'])
def index():
    excuse = None
    exc_id = None
    proof_url = None
    history = list_excuses(5)

    if request.method == 'POST':
        if 'generate' in request.form:
            scenario = request.form['scenario']
            criticality = request.form['criticality']
            with_proof = 'with_proof' in request.form
            proof_type = request.form.get('proof_type') if with_proof else None

            exc_id, excuse = generate_excuse(scenario, criticality, with_proof, proof_type)

            if with_proof and proof_type:
                proof_url = generate_proof_file(excuse, proof_type)

        elif 'rate' in request.form:
            exc_id = int(request.form['excuse_id'])
            rating = int(request.form['rating'])
            rate_excuse_in_db(exc_id, rating)
            return redirect(url_for('index'))

        elif 'clear' in request.form:
            conn = sqlite3.connect(DB_PATH)
            conn.execute('DELETE FROM excuses')
            conn.commit()
            conn.close()
            return redirect(url_for('index'))

    return render_template('index.html', scenarios=SCENARIOS, criticalities=CRITICALITY,
                           excuse=excuse, excuse_id=exc_id, history=history, proof_url=proof_url)

if __name__ == '__main__':
    app.run(debug=True)
