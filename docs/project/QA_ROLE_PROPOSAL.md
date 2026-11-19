# Quality Assurance (QA) Role Proposal

This document outlines the potential addition of a **Quality Assurance (QA)** role to the BananaVision system. This proposal is intended for later review if the capstone project requires expanded Role-Based Access Control (RBAC) and more complex business workflows.

## 1. Business Justification for a QA Role

In a real-world agricultural or supply chain facility, the person managing the IT system (Admin) is rarely the same person inspecting the fruit. A dedicated QA Specialist focuses on human-in-the-loop validation, defect tracking, and supplier accountability. 

Currently, the `Admin` role absorbs these responsibilities (e.g., reviewing flagged scans on the Quality Control page). Splitting this into a dedicated `QA` role adds realism and enterprise-grade structure to the system.

## 2. Proposed Functionalities for the QA Role

If a QA role is implemented, the following features would maximize its value and differentiate it from the standard Operator and Admin roles:

### A. Manual Defect Tagging & Annotation
*   **Current State:** The AI detects Cultivar and Ripeness.
*   **Proposed QA Feature:** When reviewing a scan, the QA user can manually tag specific physical defects that the AI might miss (e.g., *Crown Rot, Bruising, Chilling Injury, Scarring, Insect Damage*).
*   **Value:** Acknowledges AI limitations and provides a mechanism to build a dataset for training future defect-detection AI models.

### B. Batch-Level Quality Grading (Accept/Reject Workflow)
*   **Current State:** Delivery Intakes (batches) have a status of Active or Depleted.
*   **Proposed QA Feature:** After Operators scan a sample from a new Delivery Intake, the QA user reviews the aggregate data and assigns an overall **Quality Grade** (e.g., *Grade A, Grade B, Reject*) to the entire batch.
*   **Value:** If a batch is "Rejected," the system could automatically lock those bananas from being marked as "Sold" and alert the Admin, simulating a realistic supply-chain workflow.

### C. AI Feedback Loop (Human-in-the-Loop Validation)
*   **Current State:** The Admin can "override" a flagged scan, which only changes the local record.
*   **Proposed QA Feature:** The system randomly selects 5% of *high-confidence* (unflagged) scans and routes them to a "QA Audit Queue." The QA user explicitly marks the AI's result as "Correct" or "Incorrect."
*   **Value:** Enables an "Export for Retraining" feature that downloads all "Incorrect" scans and their images, creating a closed-loop Machine Learning pipeline where the system gathers data to improve itself.

### D. Supplier Claim / Rejection Reports
*   **Current State:** The system tracks suppliers and intakes, but lacks dispute mechanisms.
*   **Proposed QA Feature:** If a QA user identifies a poor-quality batch, they can generate a "Supplier Claim Report." This would be a clean PDF or printable view containing the supplier's batch number, AI scan images showing defects, and temperature readings.
*   **Value:** Provides concrete proof for refunds or supplier disputes, adding significant business value to the capstone.

### E. Intervention Recommendations
*   **Current State:** The system predicts spoilage days based on temp/humidity and treatment.
*   **Proposed QA Feature:** If the Spoilage AI predicts a batch will spoil in < 2 days while in the warehouse, it triggers a "QA Alert." The QA user logs a "Required Action" (e.g., *Action: Move batch to colder storage* or *Action: Prioritize for immediate sale*).
*   **Value:** Shifts the system from purely *monitoring* to being *prescriptive and actionable*.

## 3. Implementation Impact

Adding this role would require architectural changes:
1.  **Database:** Creating a `qa_profile` table (similar to `operator_profile` and `admin_profile`) and updating `RoleEnum` in the database and frontend.
2.  **API Security:** Updating backend dependencies (`deps.py`) to restrict/allow access to QA-specific routes.
3.  **Frontend Layout:** Updating the sidebar and routing logic in `App.tsx` and `AuthContext.tsx` to conditionally render QA tools.

**Recommendation:** Review project timelines and grading rubrics before proceeding. If time is tight, the current architecture where `Admin` acts as a "Super User" is perfectly sufficient for a Minimum Viable Product (MVP).
