import os
import time
from collections import defaultdict, deque

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

FRONTEND_ORIGIN = "https://cassava-crop-doctor.onrender.com"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Basic in-memory limit to discourage accidental abuse.
requests_by_ip = defaultdict(deque)


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin == FRONTEND_ORIGIN:
        response.headers["Access-Control-Allow-Origin"] = FRONTEND_ORIGIN
        response.headers["Vary"] = "Origin"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/")
def health():
    return jsonify({
        "service": "Cassava Crop Doctor API",
        "status": "online",
        "ai_configured": bool(GEMINI_API_KEY),
    })


@app.route("/api/diagnose", methods=["POST", "OPTIONS"])
def diagnose():
    if request.method == "OPTIONS":
        return "", 204

    if not GEMINI_API_KEY:
        return jsonify({
            "error": "AI is not configured yet. Please try again later."
        }), 503

    now = time.time()
    ip = request.remote_addr or "unknown"
    recent = requests_by_ip[ip]

    while recent and now - recent[0] > 3600:
        recent.popleft()

    if len(recent) >= 5:
        return jsonify({
            "error": "Too many assessments from this connection. Please try again later."
        }), 429

    photo = request.files.get("photo")
    if not photo:
        return jsonify({"error": "Please upload a leaf photo."}), 400

    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    mime_type = (photo.mimetype or "").lower()

    if mime_type not in allowed_types:
        return jsonify({
            "error": "Please use a JPEG, PNG, or WebP photo."
        }), 400

    image_bytes = photo.read(8 * 1024 * 1024 + 1)
    if not image_bytes or len(image_bytes) > 8 * 1024 * 1024:
        return jsonify({
            "error": "The photo is empty or too large. Choose an image under 8 MB."
        }), 400

    symptoms = (request.form.get("symptoms") or "Not specified").strip()[:300]
    recent.append(now)

    prompt = f"""
You are a cautious agricultural information assistant helping cassava
farmers in Nigeria.

Examine the attached image. User-observed symptoms: {symptoms}

Respond in plain, simple English using these headings:
1. What I can see
2. Possible cause
3. Confidence and limitations
4. Safe next steps
5. When to contact an agricultural extension officer

Consider cassava mosaic disease, cassava brown streak disease, cassava
bacterial blight, pests, nutrient or environmental problems, and other
possibilities when appropriate. Do not force a disease label if evidence
is weak. A photograph alone cannot reliably confirm every cassava disease,
especially root symptoms or diseases with similar leaf symptoms.

Do not invent a numerical probability or claim laboratory confirmation.
Do not prescribe pesticides, dosages, or chemical mixtures. Recommend
safe observation, clean tools, checking nearby plants, and qualified local
agricultural advice where appropriate. If the image is not clearly a
cassava leaf or is too blurry, say so and request a better photo.
Make clear that this is a preliminary AI assessment, not a confirmed diagnosis.
"""

    import base64

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }},
            ]
        }]
    }

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent"
    )

    try:
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": GEMINI_API_KEY,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
    except requests.RequestException:
        return jsonify({
            "error": "The AI service could not be reached. Please try again."
        }), 502

    if response.status_code != 200:
        if response.status_code == 429:
            return jsonify({
                "error": "The AI service is busy or its request limit was reached. Please try later."
            }), 429
        if response.status_code in (400, 403, 404):
            app.logger.warning(
                "AI provider returned HTTP %s", response.status_code
            )
            return jsonify({
                "error": "The AI model or API configuration needs checking."
            }), 502
        app.logger.warning("AI provider returned HTTP %s", response.status_code)
        return jsonify({"error": "The AI assessment failed. Please try later."}), 502

    try:
        data = response.json()
        parts = data["candidates"][0]["content"]["parts"]
        answer = "\n".join(
            part["text"] for part in parts if isinstance(part.get("text"), str)
        ).strip()
    except (ValueError, KeyError, IndexError, TypeError):
        return jsonify({
            "error": "The AI returned an unreadable result. Please try again."
        }), 502

    if not answer:
        return jsonify({"error": "The AI returned an empty result."}), 502

    return jsonify({
        "assessment": answer,
        "disclaimer": "Preliminary AI guidance only; not a confirmed diagnosis.",
    })


@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Photo exceeds the 8 MB upload limit."}), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
