# Arthentic iPhone Mobile Prototype

High-fidelity mobile prototype of the **Arthentic** canvas physical fingerprint authentication system for iPhone 12 Pro (LiDAR), built with **Flutter + Swift ARKit**, backed by a **FastAPI** server that executes feature matching and signs **EIP-712** attestations.

---

## Architecture

- **`app/`**: Flutter mobile application matching the design reference (`Verify`, `Scan Surface`, `Result`, and `Wallet` screens).
  - Native iOS module: `CaptureChannel.swift` utilizing ARKit `sceneDepth` & AVFoundation.
  - Mock/Simulator fallback mode: Runs smoothly on physical devices, simulators, and unit tests.
- **`server/`**: Python FastAPI backend:
  - `crypto/sun.py`: NTAG 424 DNA SUN simulation with anti-replay counter tracking.
  - `crypto/attestation.py`: EIP-712 typed data signing engine.
  - `ml/`: Photo weave embedding, LiDAR plane fitting & roughness stats, flatness gate.
  - `routes/`: Auth, verify (Level 1 & Level 2), captures, genesis, provenance.
- **`fixtures/`**: Synthetic capture datasets and calibration test scripts (`calibrate.py`).

---

## Quickstart

### 1. Run the Python Backend Server
```bash
# In project root:
source server/venv/bin/activate
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```
API docs available at: `http://localhost:8000/docs`

### 2. Run Backend Unit Tests
```bash
PYTHONPATH=. server/venv/bin/pytest server/tests
```

### 3. Run Calibration Benchmark (Milestone 4)
```bash
PYTHONPATH=. server/venv/bin/python3 fixtures/calibrate.py
```
**Results:**
- Same Surface (Genuine): ~98.2% (Pass)
- Different Surface (Impostor): ~73.1% (Rejected below 88% threshold)
- Flat-Print Attack (Paper print): ~36.7% (Rejected by flat-print check)

### 4. Run the Flutter Mobile App
```bash
cd app
flutter test          # Runs widget smoke and navigation tests
flutter run           # Runs on connected iPhone 12 Pro or iOS Simulator
```

