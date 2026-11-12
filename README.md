# AI-Powered KYC Verification System

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
ADMIN_USERNAME=admin
ADMIN_PASSWORD=use-a-long-unique-password
SECRET_KEY=generate-a-long-random-secret
```

The admin section is available at `/admin/login`. Dashboard APIs require the bearer token issued
after login. Admins can correct extracted identity fields and record an approval or rejection with
a required reason. Corrections and decisions are timestamped in the record's `admin_audit` history;
manual decisions are marked with `decision_source: MANUAL` and preserve the original automated
decision in `automated_decision_snapshot`. Set unique credentials and a random secret before use.

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

### Admin API

`POST /api/admin/login` accepts the configured `ADMIN_USERNAME` and `ADMIN_PASSWORD`; use its
returned bearer token for `/api/verification-history`, `/api/stats`, deletion, and the admin mutation
routes. `/api/verification/{session_id}` is also admin-authenticated; applicants see a submission
confirmation after the liveness step, while detailed verification results are available in the admin area.

`PUT /api/admin/verification/{session_id}/details` corrects extracted fields and requires a reason.
`PUT /api/admin/verification/{session_id}/decision` accepts `APPROVED` or `REJECTED` and requires
a reason. Both actions are added to the audit history.

### `GET /api/verification-history` (admin bearer token required)

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

Decisions are made on the backend only, from layered evidence (details in
[Evidence-based verification](#evidence-based-verification-v2) below).

```
Document status   VALID | INVALID | SUSPICIOUS | VERIFICATION_UNAVAILABLE | MANUAL_REVIEW_REQUIRED
Face match        MATCH (>= FACE_SIMILARITY_THRESHOLD, default 0.32)
                  UNCERTAIN (between FACE_NO_MATCH_THRESHOLD 0.22 and the match threshold)
                  NO_MATCH (< FACE_NO_MATCH_THRESHOLD)
Liveness          PASS | UNCERTAIN | FAIL          (server-side; the browser can only tighten it)
Face alteration   LOW | REVIEW | HIGH              (heuristic risk; classifier score is informational until calibrated)

Final KYC status, most severe first:
  SUSPICIOUS               document SUSPICIOUS, QR/printed-photo mismatch, or liveness FAIL
  REJECTED                 document INVALID, or face NO_MATCH
  MANUAL_REVIEW_REQUIRED   capture unusable (retake), UNCERTAIN face/liveness, any alteration signal, document needs a human
  VERIFICATION_UNAVAILABLE document needs an authoritative source/key that was unavailable
  VERIFIED                 OCR read confidence rounds to 100% + face MATCH + liveness PASS, unless a document is INVALID/SUSPICIOUS or other suspicious signal exists
```

Legacy `final_decision` is kept for the admin views: VERIFIED -> APPROVED, REJECTED/SUSPICIOUS -> REJECTED,
everything else -> PENDING. The old "document confidence score" is now shown as *OCR read confidence*: it says
how well the document was read, not whether it is authentic.

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

| Document | Detected by | Local validation | What can make it VALID |
|---|---|---|---|
| Aadhaar | keywords / 12-digit groups / QR | Verhoeff checksum, Secure QR decode, QR vs OCR | verified UIDAI QR signature + data matches |
| PAN | headings / PAN pattern | format + holder-type letter, surname initial, layout | `PAN_*` provider match |
| Passport | MRZ / "PASSPORT" | ICAO 9303 TD3 MRZ check digits, expiry, OCR vs MRZ | `PASSPORT_*` provider match |
| Driving licence | headings / number pattern | SS RR YYYY NNNNNNN structure, state code, dates | `DL_*` provider match |
| Citizenship | "Citizenship" | country-aware (Nepal), plausibility checks | `CITIZENSHIP_*` provider match |
| 10th / 12th result | board / marksheet keywords | field extraction, marks arithmetic, year | `EDUCATION_*` provider match |
| College ID / unknown | keywords | none | always `MANUAL_REVIEW_REQUIRED` |

---

## Phase 2 Roadmap (Future)

- Certified presentation-attack and deepfake models validated on target cameras and populations
- Behavioral biometrics
- Graph-based fraud detection
- Risk scoring engine
- Multi-factor verification
- Real-time video liveness (MediaPipe)

---

## Evidence-based verification (v2)

The system distinguishes **"I read this document"** from **"I have evidence this document is authentic"**.
OCR success, regex/format validity and MRZ check digits are *necessary but never sufficient*.

```
Upload -> type detection -> image quality -> OCR -> document-specific validation
       -> cryptographic / QR / MRZ -> external provider -> tamper analysis -> decision engine
       -> (live capture) liveness -> face match -> face-alteration analysis -> final KYC status
```

Document status `VALID` still requires **authoritative evidence**: a verified UIDAI QR signature or a genuine
(non-mock) match from a configured external provider, plus the document's required local checks. Overall KYC
status `VERIFIED` can also result from the local rule of OCR read confidence that rounds to 100%, face `MATCH`, and liveness
`PASS`, provided no document `INVALID`/`SUSPICIOUS` status or other suspicious signal exists. In that case the
status message identifies that it was based on local checks; it does not claim issuer authenticity. When the
local rule is not met and an authoritative provider is unavailable, the result remains
`VERIFICATION_UNAVAILABLE`. Mock provider results remain labelled `MOCK_VERIFICATION` and are disabled when
`APP_ENV=production`.

### Code map (`backend/services/kyc/`)

| File | Role |
|---|---|
| `result.py` | unified result schema (`DocumentVerification`, checks, evidence level) |
| `engine.py` | document decision rules and risk score |
| `identity.py` | final decision: document + face + liveness + alteration |
| `documents/` | per-document verifiers (`aadhaar`, `pan`, `passport` + `mrz`, `driving_licence`, `citizenship`, `education`) |
| `providers/` | provider interfaces, generic REST adapter, mock, registry |
| `external.py` | runs the provider, compares returned identity, never raises into the workflow |
| `quality.py`, `tampering.py` | image-quality gate; document tamper heuristics |
| `liveness.py`, `deepfake.py` | presentation-attack and face-alteration heuristics |
| `config.py` | all env-driven settings and thresholds |

### What you need to run

**Required:** MongoDB (local or Atlas -> `MONGODB_URL`), `cp backend/.env.example backend/.env`, backend and
frontend dependencies (first run downloads the EasyOCR and ArcFace models). With nothing else configured the app
runs and reads documents, but every document ends `VERIFICATION_UNAVAILABLE` or `MANUAL_REVIEW_REQUIRED`.

**Aadhaar - UIDAI certificate (free).** Download UIDAI's *production* Secure QR / offline e-KYC public-key
certificate(s) from uidai.gov.in (named like `uidai_offline_publickey_<date>.cer`) and put them in
`backend/certs/uidai/`, or set `AADHAAR_CERTIFICATE_PATH`. UIDAI rotated this key over the years, so add every
certificate you can find; each QR is checked against all. Staging/test certificates are ignored on purpose. The
`.cer` currently in that folder is a staging certificate, so Aadhaar cannot reach `VALID` until you add the
production one.

**PAN, passport, driving licence, citizenship, education - external APIs (paid / onboarding).** Set, per kind, in
`backend/.env` only (never in the frontend):

```env
PAN_API_URL=         PAN_API_KEY=
PASSPORT_API_URL=    PASSPORT_API_KEY=
DL_API_URL=          DL_API_KEY=
CITIZENSHIP_API_URL= CITIZENSHIP_API_KEY=
EDUCATION_API_URL=   EDUCATION_API_KEY=
```

`<KIND>_PROVIDER` can be `none`, `generic` (default when URL and key are set) or `mock` (development only).
Optional tuning per kind: `_API_AUTH_HEADER`, `_API_AUTH_SCHEME`, `_API_TIMEOUT_S`, `_API_RETRIES`,
`_API_STATUS_KEY`, `_API_VALID_VALUES`, `_API_NOT_FOUND_VALUES`, `_API_NAME_KEY`, `_API_DOB_KEY`.
Public APIs for these documents generally do not exist; you need an authorised verification provider, and for
Nepal citizenship certificates and board results I know of no public API. If none is configured those documents
are reported as "appears valid, not verified against an authoritative source".

#### Using Surepass (or any other vendor)

Surepass offers PAN, driving licence and passport (ePassport) verification APIs and says a free account includes
a sandbox; production use is billed and pricing is handled by their sales team, so do not assume it is free. Steps:

1. Create an account at surepass.io and get the sandbox token.
2. From their API reference, note per API: endpoint URL, how the token is sent (usually `Authorization: Bearer`),
   and the exact request and response JSON.
3. Put the URL and token in `backend/.env` (`PAN_API_URL`, `PAN_API_KEY`, ...).
4. Match the response shape. The generic adapter (`providers/generic_rest.py`) POSTs
   `{"document_type", "document_number", "name", "dob", ...}` and reads a `status` field plus optional `name` and
   `dob`. If the vendor's field names differ slightly, the `*_API_STATUS_KEY` / `*_NAME_KEY` / `*_VALID_VALUES`
   settings may be enough; otherwise write a small adapter subclass of `GenericRestMixin` overriding
   `build_body` (request fields) and `parse` (response mapping). Their ePassport API expects passport number,
   date of birth and expiry, which the passport request already carries.
5. Test in the sandbox, then switch to the production token.

The generic adapter has only been tested with simulated responses, not against a real vendor.

### Face match, liveness and deepfake analysis

**Face match** uses the existing aligned ArcFace embeddings with cosine similarity, now with three outcomes
(`MATCH` / `UNCERTAIN` / `NO_MATCH`) driven by `FACE_SIMILARITY_THRESHOLD` and `FACE_NO_MATCH_THRESHOLD`.

**Liveness** (`liveness.py`, server-side) is passive signal processing on the live frame and an optional burst of
extra frames: periodic screen/moire patterns (FFT peak prominence), specular glare, flat texture, colourless faces
(black-and-white prints), and identical frames (static image or frozen replay). The browser's challenge result is
advisory: it can downgrade a PASS to UNCERTAIN but can never override a failure. Each server-issued head-turn
challenge asks for a baseline, then one left and one right turn in randomized order. Each turn must reach at least
`0.12` normalized yaw change in the requested direction (left is negative and right is positive in captured image
coordinates; configurable with `LIVENESS_MIN_TURN_RATIO`); a larger
turn also passes, so the value is a minimum, not an exact target. This is still a heuristic check, not certified PAD.

**Face-alteration / deepfake analysis** (`deepfake.py`) runs after liveness on **only the live camera frame** (using the face
box found by MTCNN). It combines four local image-forensics signals with a pretrained ONNX ViT image classifier
(`ChrisBeischl/LoRA-deepfake-detection`, quantized model). The classifier weights are downloaded from Hugging Face
on first use and cached locally; `onnxruntime` and `huggingface_hub` are installed with `backend/requirements.txt`.
Set `DEEPFAKE_MODEL_REPO` and `DEEPFAKE_MODEL_FILE` to override the model source. If model loading or inference fails,
the result reports that only heuristic analysis was available. The classifier's raw score is recorded for evaluation,
but is not used by itself to raise the LOW/REVIEW/HIGH level or mark a verification suspicious until calibrated on
representative webcam samples. It does **not** inspect the photo printed on the document; a swapped document photo is covered
by the document tamper heuristics and, for Aadhaar, by comparing the printed photo with the photo inside the signed
QR. The local heuristic component uses four signals, each scored 0-1 and combined as `risk = 1 - prod(1 - weight x signal)`:

| Signal | Weight | Idea |
|---|---|---|
| noise mismatch | 0.6 | sensor-noise level of the face vs patches outside the face box |
| skin-tone break | 0.6 | Lab colour jump between face and neck (blended swaps) |
| recompression mismatch | 0.5 | JPEG error level of the face vs the whole frame (spliced content) |
| spectral anomaly | 0.5 | high- vs mid-frequency FFT energy of the face (generator up-sampling) |

The heuristic component produces `LOW`, `REVIEW` or `HIGH` using thresholds
`DEEPFAKE_REVIEW_THRESHOLD` and `DEEPFAKE_HIGH_RISK_THRESHOLD`. Any `REVIEW` or `HIGH` alteration signal, including
an elevated classifier score, routes the overall result to `MANUAL_REVIEW_REQUIRED`; it does not by itself mark the
person or capture `SUSPICIOUS`. The classifier score remains informational until calibrated.
The selected model card describes training on real Flickr portraits and StyleGAN2
generated faces, so it may miss newer generators, face swaps, or other manipulation methods; its reported test
metrics are from that model's dataset, not this project. It is a review signal, not proof of fraud or authenticity.
Validate and calibrate it on representative camera captures before relying on automated decisions. The face match
remains a separate check against the document photo.

**Document tamper analysis** (`tampering.py`) checks editing-software metadata, JPEG error-level inconsistencies and
regional noise differences. It can raise suspicion; a clean result never proves authenticity.

### Other environment variables

`FACE_NO_MATCH_THRESHOLD`, `LIVENESS_ATTACK_THRESHOLD`, `LIVENESS_UNCERTAIN_THRESHOLD`,
`LIVENESS_MIN_TURN_RATIO`,
`DEEPFAKE_HIGH_RISK_THRESHOLD`, `DEEPFAKE_REVIEW_THRESHOLD`, `DEEPFAKE_MODEL_REPO`, `DEEPFAKE_MODEL_FILE`,
`TAMPER_SUSPICIOUS_THRESHOLD`,
`OCR_LANGUAGES` (use `en,ne` to read Devanagari, e.g. Nepal citizenship), `MAX_FILE_SIZE_MB`. All are listed in
`backend/.env.example`.

### Security and privacy

API keys exist only in backend env vars: never sent to the frontend, logged, or returned by any API (the provider
name is stored server-side only). Uploads are identified by magic bytes, size-capped, decoded and dimension-checked;
the client filename and Content-Type are ignored. Identifiers are stored masked (last 4 only). Logs record status,
document type, provider category, timing and error category, never personal data. `backend/uploads/` holds identity
images and faces: it is git-ignored, but files committed earlier stay tracked until you run
`git rm -r --cached backend/uploads`.

### Limitations

- Liveness is heuristic, and the deepfake model is a research classifier (see above); neither is a certified detector.
- No vendor adapter is bundled; the generic REST adapter needs a real contract (or a small subclass).
- Passports: TD3 MRZ only. Driving licences: India-structured numbers. Nepal Bikram Sambat dates are checked for
  plausibility, not converted.
- Documents with no authoritative source (college ID, unknown, unsupported countries) always need manual review.
- Admin dashboard filters and pie chart still use the legacy APPROVED/REJECTED/PENDING values.

### Tests

```bash
cd backend && pip install -r requirements-dev.txt && pytest
```

The suite (135 tests) covers Aadhaar signing/verification with real RSA keys, MRZ, PAN, driving licence,
citizenship, education, every provider failure mode, the decision matrix, the face pipeline with a stubbed
model, and upload validation. It does not run the real OCR, ArcFace or MTCNN models, MongoDB, or a browser.
