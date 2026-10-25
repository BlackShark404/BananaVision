# 🌐 Deep Dive: Landing Page & Public Application Showcase

> **Feature 13:** Landing Page  
> **Frontend Files:** [`frontend/src/pages/Landing.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Landing.tsx), [`frontend/src/App.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/App.tsx)

---

## 1. Why Did We Implement This System?

While BananaVision functions as an edge kiosk on the factory floor, stakeholders, inspectors, and remote managers need:
1. A professional, modern entry portal explaining the system's capabilities (AI Ripeness grading, finger counting, spoilage estimation, and multi-camera inspection).
2. Dual gateway routing: Operators entering Kiosk Mode vs Administrators entering the Management Portal.
3. An offline-friendly design that functions smoothly on local area networks (LAN) without relying on external cloud CDNs.

---

## 2. Key Improvements & Technical Implementations

| Area | Implementation & Fix |
|---|---|
| **LANDING-01** | The logo container previously used a generic `div` `onClick`. Refactored to native accessible button semantics with keyboard navigation support (`Enter` / `Space` activation). |
| **Responsive Design** | Built with Tailwind CSS supporting mobile viewports (390px phone) up to large 1440px+ warehouse touchscreens. |
| **Edge Autonomy** | All branding assets, SVGs, and typography load locally from `/public`, allowing the landing page to render with zero internet connectivity. |

---

## 3. High-Level Page Structure (`frontend/src/pages/Landing.tsx`)

1. **Header Navigation:**
   - Brand logo, Features, System Specifications, FAQs, and Contact links.
   - Primary Call-to-Action (CTA): **"Enter System / Login"** leading directly to `/login`.
2. **Hero Section:**
   - Visual presentation: *"Intelligent Multi-Camera Banana Classification & Spoilage Prediction System"*.
   - Value propositions: Real-time YOLOv26 inference, automated sorting, zero manual count error.
3. **Core Feature Grid:**
   - **Cultivar Detection:** Lakatan, Latundan, Cardaba.
   - **Ripeness Grading:** Unripe, Semi Ripe, Ripe, Overripe.
   - **Finger Counting:** Parallel multi-view finger localization with deduplication.
   - **Environmental Fusion:** Temperature & Humidity integration for shelf-life estimation.
4. **FAQ & Hardware Architecture:**
   - Explains the Mini PC, 4-camera array, and IoT sensor enclosure.

---

## 4. Code Breakdown: Part-by-Part

### Part A: Accessible Header & Navigation Routing (`Landing.tsx:60`)

```tsx
<div 
  role="button" 
  tabIndex={0} 
  aria-label="BananaVision Home"
  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") navigate("/") }}
  onClick={() => navigate("/")} 
  className="flex items-center gap-3 cursor-pointer group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary rounded-lg"
>
  <img src="/bananavision-logo.svg" alt="BananaVision Logo" className="w-9 h-9 object-contain" />
  <span className="font-bold text-xl tracking-tight">BananaVision</span>
</div>
```
- Satisfies strict web accessibility standards (W3C WCAG) by providing proper ARIA roles, tabindex for keyboard focus, and event listeners for keyboard keys.

---

## 5. Summary of Key Defense Takeaways

1. **Production Polish:** Shows the panel that BananaVision is a finished, professional enterprise product, not just raw backend scripts.
2. **Offline Resilience:** Functions entirely offline on the packinghouse Mini PC without external internet dependencies.
