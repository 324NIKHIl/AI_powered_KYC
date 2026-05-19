# AI-Powered KYC Verification System — Phase 1

> Document OCR + Face Verification using EasyOCR, MTCNN, FaceNet, and FastAPI

---

## Project Structure

```
ai-powered-kyc/
│
├── backend/
│   ├── main.py                     ← FastAPI entry point
│   ├── requirements.txt
│   ├── .env.example
│   │
│   ├── api/routes/
│   │   ├── document.py             ← POST /api/upload-document
│   │   ├── face.py                 ← POST /api/face-verify
│   │   └── admin.py                ← GET  /api/verification-history, /stats
│   │
│   ├── services/
│   │   ├── ocr_service.py          ← EasyOCR extraction + field parsing
│   │   ├── document_service.py     ← Full document pipeline orchestrator
│   │   ├── face_service.py         ← MTCNN + FaceNet face comparison
│   │   └── verification_service.py ← Decision logic + MongoDB persistence
│   │
│   ├── models/
│   │   └── verification.py         ← Pydantic request/response/DB models
│   │
│   ├── utils/
│   │   ├── image_processing.py     ← OpenCV preprocessing utilities
│   │   └── validators.py           ← Aadhaar, PAN, Passport regex validators
│   │
│   ├── database/
│   │   └── mongodb.py              ← Motor async MongoDB connection
│   │
│   └── uploads/                    ← Auto-created; stores documents + faces
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── LandingPage.jsx
│   │   │   ├── VerificationPage.jsx    ← 5-step verification flow
│   │   │   ├── ResultPage.jsx
│   │   │   └── AdminDashboard.jsx
│   │   │
│   │   ├── components/
│   │   │   ├── Navbar.jsx
│   │   │   ├── DocumentUpload.jsx      ← Drag & drop
│   │   │   ├── WebcamCapture.jsx       ← react-webcam + liveness challenges
│   │   │   ├── ConfidenceMeter.jsx     ← Animated arc gauge
│   │   │   ├── ProgressSteps.jsx       ← Step indicator
│   │   │   └── StatusBadge.jsx
│   │   │
│   │   ├── context/VerificationContext.jsx
│   │   └── services/api.js             ← Axios API layer
│   │
│   └── package.json
│
└── README.md
```

---

## Installation

### Prerequisites

| Tool        | Version   |
|-------------|-----------|
| Python      | 3.10 – 3.11 |
| Node.js     | 18 or 20  |
| MongoDB     | 6.x (local or Atlas) |
| Git         | any       |

> **Windows Note:** `deepface` / TensorFlow install is easiest with Python 3.10.
> `face_recognition` requires `cmake` and Visual C++ Build Tools on Windows.

---

### 1. Clone / navigate to project

```bash
cd ai-powered-kyc
```

---

### 2. Backend setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (macOS / Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

> **First run:** DeepFace downloads FaceNet model weights (~90 MB) on the first request.
> EasyOCR also downloads its English model (~40 MB) on first use.
> Keep the backend running and wait for the downloads to complete.

---

### 3. Configure environment

```bash
# Copy example env file
cp .env.example .env
```

Edit `.env`:

```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=kyc_verification
FACE_SIMILARITY_THRESHOLD=0.60
DOCUMENT_CONFIDENCE_THRESHOLD=0.75
```

---

### 4. Start MongoDB

```bash
# Local instance
mongod --dbpath C:/data/db

# OR use MongoDB Atlas — paste connection string in MONGODB_URL
```

---

### 5. Start the backend

```bash
# From inside backend/
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs available at: **http://localhost:8000/docs**

---

### 6. Frontend setup

```bash
cd ../frontend

npm install

npm run dev
```

Frontend available at: **http://localhost:5173**

---

## API Reference

### `POST /api/upload-document`

Upload identity document for OCR and face extraction.

**Form data:**
- `file` — JPG / PNG / PDF
- `session_id` (optional) — reuse existing session

**Response:**
```json
{
  "session_id": "abc123",
  "document_type": "aadhaar",
  "extracted_fields": {
    "name": "Rahul Sharma",
    "dob": "15/08/1999",
    "gender": "Male",
    "id_number": "234567891234"
  },
  "field_validation": { "name": true, "dob": true, "id_number": true },
  "document_confidence_score": 0.95,
  "document_face_extracted": true,
  "message": "Document verified successfully"
}
```

---

### `POST /api/face-verify`

Compare live webcam face against document face.

**Body:**
```json
{
  "session_id": "abc123",
  "live_face_base64": "<base64 JPEG>",
  "liveness_verified": true
}
```

**Response:**
```json
{
  "session_id": "abc123",
  "face_match": true,
  "similarity_score": 0.88,
  "liveness_verified": true,
  "final_decision": "APPROVED",
  "message": "Verification APPROVED"
}
```

---

### `GET /api/verification-history`

Paginated list of all verifications.

Query params: `page`, `limit`, `decision` (APPROVED | REJECTED | PENDING)

---

### `GET /api/stats`

Aggregate statistics.

```json
{
  "total": 42,
  "approved": 35,
  "rejected": 6,
  "pending": 1,
  "approval_rate": 0.8333,
  "avg_similarity": 0.7912
}
```

---

## Technology Stack

| Layer       | Technology                        |
|-------------|-----------------------------------|
| Frontend    | React 18, Tailwind CSS, Framer Motion, Recharts |
| Backend     | FastAPI, Python 3.10              |
| OCR         | EasyOCR                           |
| Face Detect | MTCNN                             |
| Face Match  | DeepFace / FaceNet (128-d cosine) |
| Image Proc  | OpenCV, Pillow                    |
| Database    | MongoDB (async Motor driver)      |
| Webcam      | react-webcam                      |

---

## Decision Logic

```
Document Confidence Score  (weighted field validation + face extraction)
  name      → 0.25
  dob       → 0.20
  id_number → 0.35
  face_extracted → 0.20

Face Similarity Score  (FaceNet cosine similarity, 0.0 – 1.0)
  ≥ 0.60  →  FACE MATCH

Final Decision:
  APPROVED if:
    face_match == true
    AND document_confidence >= 0.75
    AND liveness_verified == true

  REJECTED otherwise (with specific rejection reason)
```

---

## Supported Document Types

| Document     | ID Validation       |
|--------------|---------------------|
| Aadhaar Card | 12-digit number     |
| PAN Card     | ABCDE1234F format   |
| Passport     | A1234567 format     |
| College ID   | Alphanumeric 4–12 ch|

---

## Phase 2 Roadmap (Future)

- Deepfake detection (Xception-based)
- Behavioral biometrics
- Graph-based fraud detection
- Risk scoring engine
- Multi-factor verification
- Real-time video liveness (MediaPipe)
