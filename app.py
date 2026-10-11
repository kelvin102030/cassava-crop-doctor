import os
import time
from collections import defaultdict, deque

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

FRONTEND_ORIGIN = "https://cassava-crop-doctor.onrender.com"
BREWKEG_API_KEY = os.environ.get("BREWKEG_API_KEY", "")
BREWKEG_MODEL = os.environ.get("BREWKEG_MODEL", "gemini-3-flash")

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
        "ai_configured": bool(BREWKEG_API_KEY),
    })


@app.route("/api/diagnose", methods=["POST", "OPTIONS"])
def diagnose():
    if request.method == "OPTIONS":
        return "", 204

    if not BREWKEG_API_KEY:
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

    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    image_url = f"data:{mime_type};base64,{encoded_image}"

    payload = {
        "model": BREWKEG_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": image_url, "detail": "high"},
                },
            ],
        }],
        "max_tokens": 1200,
    }

    url = "https://brewkeg.dev/v1/chat/completions"

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {BREWKEG_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        app.logger.warning("BrewKeg connection failed: %s", type(exc).__name__)
        return jsonify({
            "error": "The AI service could not be reached. Please try again."
        }), 502

    if response.status_code != 200:
        app.logger.warning(
            "BrewKeg returned HTTP %s; response: %s",
            response.status_code,
            response.text[:500],
        )
        if response.status_code == 401:
            return jsonify({
                "error": "BrewKeg authentication failed. Check the API key in Render."
            }), 502
        if response.status_code == 402:
            return jsonify({
                "error": "BrewKeg needs account credit before the assessment can run."
            }), 502
        if response.status_code == 429:
            return jsonify({
                "error": "The AI service is busy or its request limit was reached. Please try later."
            }), 429
        return jsonify({
            "error": "The AI assessment failed. Check the API service logs."
        }), 502

    try:
        data = response.json()
        answer = data["choices"][0]["message"]["content"]
        if isinstance(answer, list):
            answer = "\\n".join(
                part.get("text", "")
                for part in answer
                if isinstance(part, dict) and isinstance(part.get("text"), str)
            )
        if not isinstance(answer, str):
            answer = ""
        answer = answer.strip()
    except (ValueError, KeyError, IndexError, TypeError):
        app.logger.warning("BrewKeg returned an unreadable response.")
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
