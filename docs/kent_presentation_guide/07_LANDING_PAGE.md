# 🌐 Master Guide: Landing Page & Public Application Showcase

> **Presenter & Author:** Kent RG A. Baguio  
> **Core Focus:** Offline-First Public Showcase, Dual-Gateway Navigation, W3C WCAG Accessibility Semantics (`LANDING-01`), and Responsive Edge Enclosure UI.  
> **Frontend Files:**
> - [`frontend/src/pages/Landing.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Landing.tsx) — Main landing page component, scroll spy, hero, feature grid, and FAQ accordion
> - [`frontend/src/App.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/App.tsx) — Public vs Protected routing gateway
> - [`frontend/public/`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/public/) — Local self-hosted SVGs, logo, and offline branding assets

---

## 1. Why Did We Implement This System? (Panel Defense Rationale)

### 1.1 The Operational Purpose: Stakeholder Showcase & Gateway Routing
While sorting operators spend 95% of their working day inside Kiosk Mode (`/kiosk`), an industrial agricultural system interacts with many non-sorting stakeholders:
1. **Facility Executives & Quality Auditors:** When agricultural inspectors or supermarket retail buyers visit the banana packinghouse, they need a professional overview explaining the system's computer vision capabilities, botanical cultivars supported, and environmental sensor fusion.
2. **Dual-Gateway Entry Point:** The landing page serves as the initial route (`/`), allowing staff to select their operational context:
   - **Operators:** Launch Kiosk Mode for high-throughput scanning.
   - **Administrators & Supervisors:** Log into the Administrative Management Portal to inspect reports, calibrate cameras, and audit logs.
3. **Hardware & FAQ Transparency:** Packinghouse technicians can review the 4-camera hardware array specifications, lighting enclosure parameters, and sensor calibration details directly on screen without opening a physical PDF manual.

### 1.2 Offline-First Edge Autonomy (Zero-Cloud Resilience)
Most modern landing page templates rely heavily on external CDNs (Google Fonts, unpkg, Cloudflare icons, remote stock photos).
- If the internet connection in the packinghouse drops or is completely absent, external CDN requests timeout, rendering broken layouts and unstyled text.
- **BananaVision's Solution:** 100% self-hosted edge bundling. All Lucide icons, fonts, Tailwind CSS styles, and vector assets (`bananavision-logo.svg`) are bundled directly into the Vite build. The landing page renders flawlessly on a completely disconnected local area network.

---

## 2. High-Level Page Structure & Navigation Flow

```
[ Landing Page (/) ]
 ├── [ Sticky Header ]
 │    ├── Brand Logo (Native Accessible Button)
 │    ├── Scroll Spy Nav Links (Home, About, Features, Modules, FAQs, Contact)
 │    └── Primary CTA: "Login to System" ──> Redirects to /login
 │
 ├── [ Hero Section ]
 │    ├── Value Proposition: AI-Powered Banana Classification & Ripeness System
 │    └── Secondary CTA: "Explore System Modules" ──> Smooth scroll to #modules
 │
 ├── [ Core AI Feature Grid ]
 │    ├── Cultivar Identification: Lakatan, Latundan, Cardaba
 │    ├── Ripeness Grading: Unripe, Semi-Ripe, Ripe, Overripe
 │    ├── Multi-View Finger Counting: Geometric deduplication & rotation fallback
 │    └── Spoilage Estimation: Fused Temperature & Humidity shelf-life prediction
 │
 ├── [ System Architecture & Hardware Specs ]
 │    └── 4-Camera Array, Mini PC Enclosure, IoT Environmental Sensors
 │
 ├── [ Interactive FAQ Accordion ]
 │    └── Frequently Asked Questions on sorting speed, accuracy, and calibration
 │
 └── [ Footer ]
      └── Facility contact, version metadata, and copyright
```

---

## 3. Step-by-Step Code Walkthrough: Frontend Implementation

### Step 1: IntersectionObserver Scroll Spy in [`frontend/src/pages/Landing.tsx`](file:///d:/KENT%20EDUCATION%20PROJECTS/BananaVision/frontend/src/pages/Landing.tsx)

To make navigation smooth and responsive on both desktop and touchscreens, `Landing.tsx` uses a native browser `IntersectionObserver`:

```tsx
// frontend/src/pages/Landing.tsx (lines 38-56)
useEffect(() => {
  // Observes which section is currently centered on screen
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setActiveSection(entry.target.id) // Highlights active nav link
        }
      })
    },
    { rootMargin: "-40% 0px -40% 0px" } // 40% viewport trigger boundary
  )

  navLinks.forEach((link) => {
    const el = document.getElementById(link.id)
    if (el) observer.observe(el)
  })

  return () => observer.disconnect()
}, [])
```

---

### Step 2: Accessible Semantics & Header Routing (`LANDING-01`)

```tsx
// frontend/src/pages/Landing.tsx (lines 62-69)
<header className="sticky top-0 z-50 w-full border-b border-white/20 bg-white/70 backdrop-blur-xl">
  <div className="container mx-auto px-4 h-16 sm:h-20 flex items-center justify-between">
    
    {/* LANDING-01 Fix: Native semantic <button> with proper ARIA label */}
    <button 
      className="flex items-center gap-2 cursor-pointer bg-transparent border-none p-0" 
      onClick={() => scrollToSection("home")} 
      aria-label="Go to home section"
    >
      <div className="flex items-center justify-center">
        <img src="/bananavision-logo.svg" alt="BananaVision Logo" className="w-10 h-10 object-contain" />
      </div>
      <span className="font-bold text-lg text-foreground">BananaVision</span>
    </button>

    {/* Desktop Navigation Links */}
    <nav className="hidden lg:flex items-center gap-1">
      {navLinks.map((link) => (
        <button
          key={link.label}
          onClick={() => scrollToSection(link.id)}
          className={`px-3 py-2 text-sm font-medium rounded-md transition-colors ${
            activeSection === link.id
              ? "text-primary bg-primary/10"
              : "text-foreground/70 hover:text-primary hover:bg-primary/5"
          }`}
        >
          {link.label}
        </button>
      ))}
      <Button onClick={() => navigate("/login")} variant="default" size="sm" className="ml-2">
        Login to System
      </Button>
    </nav>
```

- **LANDING-01 Fix:** In early prototypes, the logo was wrapped in a generic `<div>` with an `onClick` handler. This violated W3C accessibility guidelines because screen readers and keyboard-only users could not tab to it. We refactored it to a native semantic `<button>` with explicit `aria-label="Go to home section"`, supporting full keyboard navigation (`Tab`, `Enter`, `Space`).

---

### Step 3: Mobile Sheet Drawer for Touchscreen Responsiveness

On smaller touchscreen displays or tablets:
```tsx
// frontend/src/pages/Landing.tsx (lines 90-112)
<div className="lg:hidden flex items-center">
  <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
    <SheetTrigger asChild>
      <Button variant="ghost" size="icon">
        <Menu className="h-5 w-5" />
        <span className="sr-only">Toggle menu</span>
      </Button>
    </SheetTrigger>
    <SheetContent side="right" className="w-70 sm:w-[320px] p-0">
      <SheetTitle className="sr-only">Navigation Menu</SheetTitle>
      <div className="flex flex-col h-full py-6 px-4">
        {navLinks.map((link) => (
          <button
            key={link.label}
            onClick={() => scrollToSection(link.id)}
            className="text-left py-3 text-base font-medium border-b border-border/50"
          >
            {link.label}
          </button>
        ))}
        <Button onClick={() => navigate("/login")} className="mt-4 w-full">
          Login to System
        </Button>
      </div>
    </SheetContent>
  </Sheet>
</div>
```

---

## 4. Key Improvements & Technical Implementations

| Area | Implementation & Technical Fix |
|---|---|
| **LANDING-01** | Refactored logo navigation from unsemantic `div` to native accessible `<button>` with full W3C keyboard navigation and screen-reader support. |
| **Edge Autonomy** | All branding graphics, SVGs, typography, and stylesheets are bundled locally in `/public` and Vite chunks; zero external CDN calls. |
| **Responsive Grid** | Built with Tailwind CSS supporting mobile smartphones (390px), warehouse tablets, and large 1440px+ touchscreen monitors. |
| **Glassmorphism Header** | Sticky backdrop-blur navigation with dynamic `IntersectionObserver` scroll spy indicating the active section in real time. |

---

## 5. Defense Cheat Sheet: Panel Traps & Winning Answers

### Question 1: "Why do you have a public landing page on an offline factory floor Mini PC?"
> **Kent's Winning Answer:**  
> "BananaVision is an end-to-end commercial system. Beyond sorting bananas in Kiosk mode, packinghouses regularly host agricultural auditors, retail buyers, and plant supervisors who need an immediate, high-level briefing on the system's capabilities, supported banana cultivars, and hardware architecture. The landing page acts as that professional gateway and directs users to either Kiosk Mode for sorting or the Administrative Portal for configuration."

### Question 2: "What happens to the landing page if the warehouse local area network has no internet access?"
> **Kent's Winning Answer:**  
> "The landing page renders 100% identically with or without internet. We intentionally avoided external Google Fonts or CDN-hosted JavaScript bundles. Every image asset, icon, stylesheet, and component is bundled locally into the Vite distribution on the Mini PC's solid-state drive. It has zero external dependencies."

### Question 3: "What accessibility features did you implement on the landing page?"
> **Kent's Winning Answer:**  
> "We implemented W3C WCAG accessibility standards under **LANDING-01**. We replaced unsemantic `div` click handlers with native HTML `<button>` elements, added explicit `aria-label` tags, ensured minimum touch-target sizing for warehouse touchscreens, and implemented keyboard navigation support so all navigation links can be activated using standard `Tab`, `Enter`, and `Space` keys."
