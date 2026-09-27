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
FACE_SIMILARITY_THRESHOLD=0.32
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
  "aadhaar_qr": null,
  "message": "Document verified successfully"
}
```

For Aadhaar documents, `aadhaar_qr` holds the Secure QR result when the QR code is visible in the uploaded image (see below).

---

### `POST /api/upload-aadhaar-qr`

Upload the side of an Aadhaar card that carries the Secure QR code (the back of PVC cards).

**Form data:**
- `file` — JPG / PNG / PDF
- `session_id` — session returned by `/api/upload-document`

**Response:**
```json
{
  "found": true,
  "qr_format": "secure_v2",
  "signature_status": "verified",
  "signing_certificate": "uidai_offline_publickey.cer",
  "fields": { "name": "Rahul Sharma", "dob": "15-08-1999", "gender": "M", "aadhaar_last4": "1234",
              "district": "Pune", "state": "Maharashtra", "pincode": "411001" },
  "field_checks": { "name": "match", "dob": "match", "gender": "match", "aadhaar_last4": "match" },
  "photo_path": "uploads/faces/qr_face_abc123_1f2e3d4c.jpg",
  "tamper_flags": [],
  "message": "Aadhaar QR signature verified with UIDAI's certificate — card details match"
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

## Aadhaar Secure QR Verification

Every Aadhaar card and e-Aadhaar issued since 2019 carries a **Secure QR code** digitally
signed by UIDAI (RSA-2048 / SHA-256). It contains the holder's name, DOB, gender, partial
address, the last 4 digits of the Aadhaar number, and their **enrolment photo**.

The system decodes it (`services/aadhaar_qr_service.py`) and:

1. **Verifies UIDAI's signature offline.** A forged or edited QR code fails.
2. **Cross-checks the signed data against OCR.** An edited name, DOB, gender or Aadhaar number on the printed card is flagged. Only fields that OCR itself validated are compared, so misreads don't count as tampering.
3. **Compares the printed photo with the signed QR photo.** Both come from the same enrolment, so a mismatch means the photo was swapped, the most common Aadhaar forgery.

Any tampering indicator rejects the verification with reason *"Document appears tampered"*.
If no printed photo could be found, the QR photo is used as the reference for the selfie.

**Setup:** put UIDAI's public-key certificate(s) in `backend/certs/uidai/` (see the README
there). Without them, QR data is still decoded and cross-checked, but the signature status is
`unverified`.

**Where the QR is:** on e-Aadhaar prints it is on the same page and is read automatically.
On PVC cards it is on the back; the verification page offers an optional upload for that side.
Old pre-2019 cards carry an unsigned XML QR, which is decoded and cross-checked but reported as `unsigned`.

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




 File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/trackable/base.py", line 204, in _method_wrapper
    result = method(self, *args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/keras/engine/functional.py", line 116, in __init__
    self._init_graph_network(inputs, outputs)
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/trackable/base.py", line 204, in _method_wrapper
    result = method(self, *args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/keras/engine/functional.py", line 152, in _init_graph_network
    self._validate_graph_inputs_and_outputs()
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/keras/engine/functional.py", line 694, in _validate_graph_inputs_and_outputs
    layer = x._keras_history.layer
            ^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'KerasHistory' object has no attribute 'layer'
2026-09-27 22:36:12,945 INFO [services.verification_service] [2d5befa24cef4d659fc08f1e9ffec9e2] Face match=False similarity=0.0000 reason=Face comparison failed due to a processing error — please retry
2026-09-27 22:36:12,946 INFO [services.verification_service] [2d5befa24cef4d659fc08f1e9ffec9e2] Live face saved: uploads/faces/live_2d5befa24cef4d659fc08f1e9ffec9e2_175e64a4.jpg
2026-09-27 22:36:12,946 INFO [services.verification_service] [2d5befa24cef4d659fc08f1e9ffec9e2] Final decision=REJECTED verified=False reason=Face comparison failed due to a processing error — please retry similarity=0.0000 liveness=True
2026-09-27 22:36:12,947 INFO [services.verification_service] [2d5befa24cef4d659fc08f1e9ffec9e2] Face verify API response={'session_id': '2d5befa24cef4d659fc08f1e9ffec9e2', 'verified': False, 'face_match': False, 'similarity_score': 0.0, 'liveness_verified': True, 'final_decision': <VerificationStatus.REJECTED: 'REJECTED'>, 'status': 'rejected', 'rejection_reason': 'Face comparison failed due to a processing error — please retry', 'reason': 'Face comparison failed due to a processing error — please retry', 'message': 'Verification REJECTED — Face comparison failed due to a processing error — please retry'}
2026-09-27 22:36:12,948 INFO [api.routes.face] [2d5befa24cef4d659fc08f1e9ffec9e2] Face verify response={'session_id': '2d5befa24cef4d659fc08f1e9ffec9e2', 'verified': False, 'face_match': False, 'similarity_score': 0.0, 'liveness_verified': True, 'final_decision': <VerificationStatus.REJECTED: 'REJECTED'>, 'status': 'rejected', 'rejection_reason': 'Face comparison failed due to a processing error — please retry', 'reason': 'Face comparison failed due to a processing error — please retry', 'message': 'Verification REJECTED — Face comparison failed due to a processing error — please retry'}
INFO:     127.0.0.1:64304 - "POST /api/face-verify HTTP/1.1" 200 OK
2026-09-27 22:36:12,962 INFO [api.routes.admin] [2d5befa24cef4d659fc08f1e9ffec9e2] Result detail response final_decision=REJECTED verified=False similarity=0.0 reason=Face comparison failed due to a processing error — please retry
INFO:     127.0.0.1:64307 - "GET /api/verification/2d5befa24cef4d659fc08f1e9ffec9e2 HTTP/1.1" 200 OK
2026-09-27 22:36:12,973 INFO [api.routes.admin] [2d5befa24cef4d659fc08f1e9ffec9e2] Result detail response final_decision=REJECTED verified=False similarity=0.0 reason=Face comparison failed due to a processing error — please retry
INFO:     127.0.0.1:64310 - "GET /api/verification/2d5befa24cef4d659fc08f1e9ffec9e2 HTTP/1.1" 200 OK
^CINFO:     Shutting down
INFO:     Waiting for application shutdown.
2026-09-27 22:36:52,941 INFO [database.mongodb] MongoDB connection closed
INFO:     Application shutdown complete.
INFO:     Finished server process [2013]
INFO:     Stopping reloader process [1999]
(.venv) (base) apple@Nikhils-MBP backend % clear
(.venv) (base) apple@Nikhils-MBP backend % uvicorn main:app --reload --host 0.0.0.0 --port 8000
INFO:     Will watch for changes in these directories: ['/Users/apple/Desktop/major_project/ai-powered-kyc/backend']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [2395] using WatchFiles
INFO:     Started server process [2397]
INFO:     Waiting for application startup.
2026-09-27 22:37:07,029 INFO [pymongo.serverSelection] {"message": "Waiting for suitable server to become available", "selector": "Primary()", "operation": "ping", "topologyDescription": "<TopologyDescription id: 6ab94d3b76f59425785f1e65, topology_type: Unknown, servers: [<ServerDescription ('localhost', 27017) server_type: Unknown, rtt: None>]>", "clientId": {"$oid": "6ab94d3b76f59425785f1e65"}, "remainingTimeMS": 29}
2026-09-27 22:37:07,049 INFO [database.mongodb] Connected to MongoDB: mongodb://localhost:27017 / kyc_verification
2026-09-27 22:37:07,051 INFO [database.mongodb] MongoDB indexes ensured
INFO:     Application startup complete.
2026-09-27 22:38:18,713 INFO [api.routes.document] Document upload request filename=pan.jpg content_type=image/jpeg supplied_session=False
2026-09-27 22:38:18,714 INFO [api.routes.document] Document upload bytes=1254716
2026-09-27 22:38:18,714 INFO [api.routes.document] [6ec8709a01d4497c8023e5243d3d0faf] Document upload session initialized
2026-09-27 22:38:18,771 INFO [services.document_service] [6ec8709a01d4497c8023e5243d3d0faf] Document saved: uploads/documents/doc_39a08a1033ea.jpg shape=(758, 1166, 3)
2026-09-27 22:38:21,101 INFO [services.ocr_service] Initialising EasyOCR reader (first-time model load)…
/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/torch/ao/nn/quantized/dynamic/modules/rnn.py:162: UserWarning: torch.quantize_per_tensor, torch.quantize_per_channel and other quantized tensor creation functions that produce tensors with dtype torch.quint8, torch.qint8, and torch.qint32 are deprecated and will be removed in a future PyTorch release. Please see https://github.com/pytorch/pytorch/issues/184982 for more information. (Triggered internally at /Users/runner/work/pytorch/pytorch/aten/src/ATen/quantized/Quantizer.cpp:116.)
  w_ih = torch.quantize_per_tensor(
2026-09-27 22:38:23,370 INFO [services.ocr_service] EasyOCR ready
/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/torch/utils/data/dataloader.py:759: UserWarning: 'pin_memory' argument is set as true but not supported on MPS now, device pinned memory won't be used.
  super().__init__(loader)
2026-09-27 22:38:31,280 INFO [services.document_service] [6ec8709a01d4497c8023e5243d3d0faf] OCR extracted 36 text lines
2026-09-27 22:38:31,280 INFO [services.document_service] [6ec8709a01d4497c8023e5243d3d0faf] Detected document type: DocumentType.PAN
2026-09-27 22:38:31,283 INFO [services.document_service] [6ec8709a01d4497c8023e5243d3d0faf] OCR fields={'name': 'Nikhil Chaudhary', 'dob': '13/10/2006', 'gender': None, 'id_number': 'DHAPC1445P', 'address': None} validation={'name': True, 'dob': True, 'id_number': True}
/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/mtcnn/mtcnn.py:34: UserWarning: pkg_resources is deprecated as an API. See https://setuptools.pypa.io/en/latest/pkg_resources.html. The pkg_resources package is slated for removal as early as 2025-11-30. Refrain from using this package or pin to Setuptools<81.
  import pkg_resources
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 107ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 66ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 28ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 24ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 22ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 20ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 20ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 21ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 20ms/step
32/32 ━━━━━━━━━━━━━━━━━━━━ 0s 5ms/step 
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 73ms/step
2026-09-27 22:38:37,313 INFO [services.document_service] [6ec8709a01d4497c8023e5243d3d0faf] Document face saved: uploads/faces/doc_face_6ec8709a01d4497c8023e5243d3d0faf_d97eda55.jpg shape=(250, 224, 3)
2026-09-27 22:38:37,313 INFO [services.document_service] [6ec8709a01d4497c8023e5243d3d0faf] Document confidence=1.0000 threshold=0.6000
2026-09-27 22:38:37,318 INFO [api.routes.document] [6ec8709a01d4497c8023e5243d3d0faf] Upload complete type=DocumentType.PAN confidence=1.0000 face_extracted=True face_path=uploads/faces/doc_face_6ec8709a01d4497c8023e5243d3d0faf_d97eda55.jpg response={'session_id': '6ec8709a01d4497c8023e5243d3d0faf', 'document_type': <DocumentType.PAN: 'pan'>, 'extracted_fields': {'name': 'Nikhil Chaudhary', 'dob': '13/10/2006', 'gender': None, 'id_number': 'DHAPC1445P', 'address': None}, 'field_validation': {'name': True, 'dob': True, 'id_number': True}, 'document_confidence_score': 1.0, 'document_face_extracted': True, 'document_face_path': 'uploads/faces/doc_face_6ec8709a01d4497c8023e5243d3d0faf_d97eda55.jpg', 'message': 'Document verified successfully'}
INFO:     127.0.0.1:64346 - "POST /api/upload-document HTTP/1.1" 200 OK
2026-09-27 22:38:57,092 INFO [api.routes.face] [6ec8709a01d4497c8023e5243d3d0faf] Face verify request liveness_verified=True payload_chars=67104
2026-09-27 22:38:57,092 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Face verification started frontend_liveness=True
2026-09-27 22:38:57,094 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Session loaded doc_face_path=uploads/faces/doc_face_6ec8709a01d4497c8023e5243d3d0faf_d97eda55.jpg doc_confidence=1.0000 doc_threshold=0.6000 require_doc_confidence=False
2026-09-27 22:38:57,098 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Live image decoded shape=(480, 640, 3)
2026-09-27 22:38:57,103 INFO [services.face_service] Liveness score=0.3110 live=True
2026-09-27 22:38:57,103 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Liveness frontend=True server=True score=0.3110 final=True
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 23ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 22ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 21ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 18ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 18ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 21ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 70ms/step
2026-09-27 22:38:57,674 INFO [services.face_service] Document face box=[56, 55, 111, 135] conf=1.000
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 26ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 24ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 21ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 20ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 18ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 20ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 20ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
2/2 ━━━━━━━━━━━━━━━━━━━━ 0s 9ms/step 
1/1 ━━━━━━━━━━━━━━━━━━━━ 0s 19ms/step
2026-09-27 22:38:58,199 INFO [services.face_service] Live face box=[240, 181, 130, 162] conf=1.000 faces=1
2026-09-27 22:38:58,754 ERROR [services.face_service] Face verification error
Traceback (most recent call last):
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/backend/services/face_service.py", line 263, in verify_faces
    similarity = cosine_similarity(generate_embedding(doc_input), generate_embedding(live_input))
                                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/backend/services/face_service.py", line 186, in generate_embedding
    model = _get_model()
            ^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/backend/services/face_service.py", line 151, in _get_model
    _model = DeepFace.build_model(FACE_MODEL)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/deepface/DeepFace.py", line 61, in build_model
    return modeling.build_model(model_name=model_name)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/deepface/modules/modeling.py", line 59, in build_model
    model_obj[model_name] = model()
                            ^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/deepface/basemodels/ArcFace.py", line 53, in __init__
    self.model = load_model()
                 ^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/deepface/basemodels/ArcFace.py", line 67, in load_model
    base_model = ResNet34()
                 ^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/deepface/basemodels/ArcFace.py", line 117, in ResNet34
    model = training.Model(img_input, x, name="ResNet34")
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/trackable/base.py", line 204, in _method_wrapper
    result = method(self, *args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/keras/engine/functional.py", line 116, in __init__
    self._init_graph_network(inputs, outputs)
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/trackable/base.py", line 204, in _method_wrapper
    result = method(self, *args, **kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/keras/engine/functional.py", line 152, in _init_graph_network
    self._validate_graph_inputs_and_outputs()
  File "/Users/apple/Desktop/major_project/ai-powered-kyc/.venv/lib/python3.11/site-packages/tensorflow/python/keras/engine/functional.py", line 694, in _validate_graph_inputs_and_outputs
    layer = x._keras_history.layer
            ^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'KerasHistory' object has no attribute 'layer'
2026-09-27 22:38:58,756 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Face match=False similarity=0.0000 reason=Face comparison failed due to a processing error — please retry
2026-09-27 22:38:58,758 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Live face saved: uploads/faces/live_6ec8709a01d4497c8023e5243d3d0faf_689d687e.jpg
2026-09-27 22:38:58,758 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Final decision=REJECTED verified=False reason=Face comparison failed due to a processing error — please retry similarity=0.0000 liveness=True
2026-09-27 22:38:58,759 INFO [services.verification_service] [6ec8709a01d4497c8023e5243d3d0faf] Face verify API response={'session_id': '6ec8709a01d4497c8023e5243d3d0faf', 'verified': False, 'face_match': False, 'similarity_score': 0.0, 'liveness_verified': True, 'final_decision': <VerificationStatus.REJECTED: 'REJECTED'>, 'status': 'rejected', 'rejection_reason': 'Face comparison failed due to a processing error — please retry', 'reason': 'Face comparison failed due to a processing error — please retry', 'message': 'Verification REJECTED — Face comparison failed due to a processing error — please retry'}
2026-09-27 22:38:58,759 INFO [api.routes.face] [6ec8709a01d4497c8023e5243d3d0faf] Face verify response={'session_id': '6ec8709a01d4497c8023e5243d3d0faf', 'verified': False, 'face_match': False, 'similarity_score': 0.0, 'liveness_verified': True, 'final_decision': <VerificationStatus.REJECTED: 'REJECTED'>, 'status': 'rejected', 'rejection_reason': 'Face comparison failed due to a processing error — please retry', 'reason': 'Face comparison failed due to a processing error — please retry', 'message': 'Verification REJECTED — Face comparison failed due to a processing error — please retry'}
INFO:     127.0.0.1:64354 - "POST /api/face-verify HTTP/1.1" 200 OK
2026-09-27 22:38:58,767 INFO [api.routes.admin] [6ec8709a01d4497c8023e5243d3d0faf] Result detail response final_decision=REJECTED verified=False similarity=0.0 reason=Face comparison failed due to a processing error — please retry
INFO:     127.0.0.1:64357 - "GET /api/verification/6ec8709a01d4497c8023e5243d3d0faf HTTP/1.1" 200 OK
2026-09-27 22:38:58,771 INFO [api.routes.admin] [6ec8709a01d4497c8023e5243d3d0faf] Result detail response final_decision=REJECTED verified=False similarity=0.0 reason=Face comparison failed due to a processing error — please retry
INFO:     127.0.0.1:64360 - "GET /api/verification/6ec8709a01d4497c8023e5243d3d0faf HTTP/1.1" 200 OK
