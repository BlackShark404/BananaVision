# 🍌 BananaVision — Kent's Prototype Presentation & Code Defense Guide

Welcome to your complete preparation repository for tomorrow's **10–15 Minute Prototype Output Presentation** and code defense.

This documentation suite breaks down every single module you own in the **BananaVision** codebase, explaining:
- **Part-by-part code breakdowns** with exact file and line references.
- **Architectural & Security Rationales** (why each feature was designed and implemented this way).
- **Vulnerabilities Fixed** from the historical review (AUTH-01 to 04, SAVE-01/02, ADMIN-01, ROLE-01, PROFILE-01 to 03, AUDIT-01 to 03, SCANNER-01 to 03, CONFIG-01 to 03, RETENTION-01 to 03, and AI-01 to 03).
- **Deep Computer Vision Mechanics** of how YOLOv26 detection, rotation fallback, cluster suppression, and multi-camera fusion operate.

---

## 📚 Study & Presentation File Directory

| # | Document | Primary Topics Covered |
|---|---|---|
| **00** | [00_PRESENTATION_MASTER_SCRIPT.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/00_PRESENTATION_MASTER_SCRIPT.md) | **Your 10–15 minute presentation script**, screen transitions, talking points, and Q&A defense answers for panel traps. |
| **01** | [01_AUTH_LOGIN_LOGOUT_SECURITY.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/01_AUTH_LOGIN_LOGOUT_SECURITY.md) | Login, Logout, Kiosk Operator Swap, PIN Authentication, Rate Limiting (`AUTH-04`), JWT Revocation via `token_version` (`AUTH-02`), and Cryptographic Setup Tokens (`AUTH-01`). |
| **02** | [02_USER_MANAGEMENT_AND_ACCOUNTS.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/02_USER_MANAGEMENT_AND_ACCOUNTS.md) | User Creation, Account Editing, Status Toggles, Last Active Admin Safeguard (`ADMIN-01`), Role Reconciliation (`ROLE-01`), and Dedicated Password/PIN Reset (`RESET-01`). |
| **03** | [03_PROFILE_MANAGEMENT.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/03_PROFILE_MANAGEMENT.md) | Self-Service Avatar Updates (`PROFILE-01`), Old Credential Verification (`PROFILE-02`), and Lifetime SQL Aggregate Statistics (`PROFILE-03`). |
| **04** | [04_ACTIVITY_LOGS_AND_AUDITING.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/04_ACTIVITY_LOGS_AND_AUDITING.md) | Activity Log Schema, Server-Side Pagination & Dynamic Filtering (`AUDIT-01`), Security Event Auditing (`AUDIT-02`), and RFC-compliant CSV Quote Escaping (`AUDIT-03`). |
| **05** | [05_SYSTEM_AND_SCANNER_CONFIG.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/05_SYSTEM_AND_SCANNER_CONFIG.md) | 4-Camera Setup, Authenticated Mapping (`SCANNER-01`), MJPEG Stream Generator, Station Lock Concurrency (`station_lock`), and System Power Management. |
| **06** | [06_DATA_RETENTION_AND_EXPORT.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/06_DATA_RETENTION_AND_EXPORT.md) | Data Retention Policy (Unreferenced capture cleanup vs scan records retention), and Streaming CSV Export vs Database Backup (`RETENTION-03`). |
| **07** | [07_LANDING_PAGE.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/07_LANDING_PAGE.md) | Landing Page showcase, Kiosk vs Management entrypoints, Accessibility fixes (`LANDING-01`), and Offline-First Mini PC packaging. |
| **08** | [08_YOLO_DETECTION_AND_AI_PIPELINE.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/08_YOLO_DETECTION_AND_AI_PIPELINE.md) | **The Core AI System**: Theory of YOLO, Two-Stage Architecture (COCO Pre-Detector + Custom Classifier), 180° Rotation Fallback, Geometric Deduplication, and Multi-Camera Botanical Harmonization. |

---

## ⚡ Quick 3-Step Strategy for Tomorrow

1. **Step 1 (Tonight):** Read [00_PRESENTATION_MASTER_SCRIPT.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/00_PRESENTATION_MASTER_SCRIPT.md) and practice your 10–15 minute pacing with a timer.
2. **Step 2:** Deep-dive into [08_YOLO_DETECTION_AND_AI_PIPELINE.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/08_YOLO_DETECTION_AND_AI_PIPELINE.md) and [01_AUTH_LOGIN_LOGOUT_SECURITY.md](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/docs/kent_presentation_guide/01_AUTH_LOGIN_LOGOUT_SECURITY.md). These are the two most technical topics panelists love to grill presenters on.
3. **Step 3 (Before Presentation):** Ensure your backend and frontend are running:
   - Backend: `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
   - Frontend: `npm run dev`
   - Log into Admin, open your tabs, and be ready to dazzle the panel!
