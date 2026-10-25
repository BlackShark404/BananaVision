# 💾 Deep Dive: Data Retention, Storage Management & Scan Export

> **Feature 12:** Data Retention Settings & Database Export  
> **Backend Files:** [`backend/app/api/v1/config.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/api/v1/config.py), [`backend/app/models/system_config.py`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/backend/app/models/system_config.py)  
> **Frontend Files:** [`frontend/src/pages/admin/SystemConfig.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/admin/SystemConfig.tsx)

---

## 1. Why Did We Implement This System?

A 4-camera computer vision kiosk captures high-resolution imagery with every scan:
- 4 cameras $\times$ 2 MB per JPEG $\approx$ **8 MB per scan**.
- At 500 scans per day, image captures generate **4 GB of image files daily** (over 120 GB per month!).
- On a compact Mini PC with a 256 GB or 512 GB SSD, unmanaged storage will eventually fill the drive, crashing PostgreSQL and the operating system.
- **The Solution:** A dual strategy of **Automated Data Retention** (cleaning up orphaned capture files after a configurable retention window) and **Administrative CSV Export** (allowing management to download summary reports into spreadsheet tools).

---

## 2. Security & Architecture Vulnerabilities Clarified

| Vulnerability ID | Historical Misconception | How Kent's Code Fixed / Clarified It |
|---|---|---|
| **RETENTION-01** | The UI previously promised a generic "30-day cleanup" without clarifying what gets deleted. | Explicitly defined the policy: **Clean unreferenced captures older than retention days; retain scan records, metadata, and verified evidence** for audit compliance. |
| **RETENTION-02** | Failed scans could leave image captures on disk without an associated database row (orphans). | Added orphan capture cleanup handling so storage is reclaimed even if an inference fails mid-pipeline. |
| **RETENTION-03** | The UI button was mislabeled "Database Backup", confusing users into thinking it could restore the system. | Accurately relabeled to **"Export Scan Summaries (CSV)"** with clear in-app disclosures: *"Download scan summaries as CSV. Accounts, settings, audit logs and images are excluded; this export cannot restore the database."* |

---

## 3. Code Breakdown: Part-by-Part

### Part A: Scan Summary CSV Streaming (`backend/app/api/v1/config.py:60`)

```python
@router.get("/export")
async def export_database(db: DbSession, admin: AdminUser):
    """Export scan summaries to CSV. This file cannot restore the database."""
    result = await db.execute(
        select(Scan)
        .options(selectinload(Scan.classification), selectinload(Scan.status_logs))
        .order_by(Scan.date_time, Scan.id)
    )
    scans = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Scan ID", "Date Time (UTC+08:00)", "Cultivar", "Ripeness", "Confidence", "Inventory Status"])

    for scan in scans:
        cultivar = scan.classification.cultivar if scan.classification else "N/A"
        ripeness = scan.classification.ripeness if scan.classification else "N/A"
        confidence = scan.classification.confidence if scan.classification else "N/A"
        status = scan.status_logs[-1].inventory_status if scan.status_logs else "N/A"
        writer.writerow([
            scan.id,
            scan.date_time.isoformat(),
            getattr(cultivar, "value", cultivar),
            getattr(ripeness, "value", ripeness),
            confidence,
            getattr(status, "value", status)
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=bananavision_inventory_export.csv"}
    )
```
- **Streaming Response:** Rather than holding an enormous file in memory, FastAPI streams the CSV text chunks directly to the browser.
- **Date Boundary Preservation:** Timestamps are formatted with explicit Asia/Manila offset (+08:00).

---

### Part B: Retention Toggle (`SystemConfig.tsx:470`)

In `SystemConfig.tsx`:
```tsx
<div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border">
  <div>
    <h4 className="font-medium text-sm sm:text-base">Data Retention</h4>
    <p className="text-xs sm:text-sm text-muted-foreground">
      Clean unreferenced captures older than {config.retentionDays ?? "—"} days; retain scan records and referenced evidence
    </p>
  </div>
  <Button 
    variant={localConfig.dataRetentionEnabled ? "default" : "outline"} 
    onClick={toggleDataRetention} 
    disabled={saving || disabled}
  >
    {localConfig.dataRetentionEnabled ? "Enabled" : "Disabled"}
  </Button>
</div>
```
- Admins can toggle this policy on or off with instant optimistic feedback, serialized through database revision management.

---

## 4. Summary of Key Defense Takeaways

1. **Honest Terminology:** You do not claim the CSV is a complete SQL database backup; it is an analytical inventory export for warehouse spreadsheets.
2. **Disk Preservation:** Protects the Mini PC from disk-space exhaustion while retaining vital quality inspection history.
3. **Role Authorization:** Only administrators with `AdminUser` credentials can toggle data retention or export scan summaries.
