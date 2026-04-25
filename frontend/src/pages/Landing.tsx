import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { CheckCircle2, Factory, BarChart3, ShieldCheck, Mail, ChevronRight, Menu, ScanLine, PackageOpen, ScrollText } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "@/components/ui/sheet"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"

const navLinks = [
  { label: "Home", id: "home" },
  { label: "About", id: "about" },
  { label: "Key Features", id: "features" },
  { label: "Modules", id: "modules" },
  { label: "FAQs", id: "faqs" },
  { label: "Contact", id: "contact" },
]

export default function Landing() {
  const navigate = useNavigate()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeSection, setActiveSection] = useState("home")
  
  const scrollToSection = (id: string) => {
    setMobileOpen(false)
    // Small delay so sheet closes before scrolling
    setTimeout(() => {
      const el = document.getElementById(id)
      if (el) {
        window.scrollTo({
          top: el.offsetTop - 80,
          behavior: "smooth"
        })
      }
    }, 150)
  }

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id)
          }
        })
      },
      { rootMargin: "-40% 0px -40% 0px" }
    )

    navLinks.forEach((link) => {
      const el = document.getElementById(link.id)
      if (el) observer.observe(el)
    })

    return () => observer.disconnect()
  }, [])

  return (
    <div className="min-h-screen bg-background flex flex-col font-sans">
      {/* Navigation Bar */}
      <header className="sticky top-0 z-50 w-full border-b border-white/20 dark:border-white/5 bg-white/70 dark:bg-background/70 backdrop-blur-xl shadow-sm">
        <div className="container mx-auto px-4 h-16 sm:h-20 flex items-center justify-between">
          <div className="flex items-center gap-2 cursor-pointer" onClick={() => scrollToSection("home")}>
            <div className="flex items-center justify-center">
              <img src="/bananavision-logo.svg" alt="Logo" className="w-10 h-10 object-contain" />
            </div>
            <span className="font-bold text-lg text-foreground">BananaVision</span>
          </div>

          {/* Desktop Nav */}
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

          {/* Mobile Nav */}
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
                <div className="flex flex-col h-full">
                  {/* Sheet Header */}
                  <div className="flex items-center gap-2 px-6 py-4 border-b bg-banana/30">
                    <div className="flex items-center justify-center">
                      <img src="/bananavision-logo.svg" alt="Logo" className="w-10 h-10 object-contain" />
                    </div>
                    <span className="font-bold text-lg">BananaVision</span>
                  </div>
                  {/* Sheet Links */}
                  <nav className="flex flex-col flex-1 px-4 py-4">
                    {navLinks.map((link) => (
                      <button
                        key={link.label}
                        onClick={() => scrollToSection(link.id)}
                        className={`text-left text-base font-medium px-3 py-3 rounded-lg transition-colors ${
                          activeSection === link.id
                            ? "text-primary bg-primary/10"
                            : "text-foreground/80 hover:text-primary hover:bg-primary/5"
                        }`}
                      >
                        {link.label}
                      </button>
                    ))}
                  </nav>
                  {/* Sheet Footer */}
                  <div className="px-6 pb-6">
                    <Button onClick={() => { setMobileOpen(false); navigate("/login") }} variant="default" className="w-full h-11">
                      Login to System
                    </Button>
                  </div>
                </div>
              </SheetContent>
            </Sheet>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Home / Hero Section */}
        <section id="home" className="relative pt-24 pb-24 lg:pt-32 lg:pb-32 overflow-hidden px-4 flex flex-col items-center justify-center min-h-[85vh]">
          {/* Enhanced Background Blurs */}
          <div className="absolute top-[-5%] left-1/2 -translate-x-1/2 w-full max-w-250 h-125 bg-primary/20 rounded-full blur-[120px] -z-10" />
          <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSI0MCIgaGVpZ2h0PSI0MCI+PHBhdGggZD0iTTAgMGg0MHY0MEgweiIgZmlsbD0ibm9uZSIvPPHBhdGggZD0iTTAgMGgxdjQwSDB6TTM5IDBoMXY0MEgzOXoiIGZpbGw9InJnYmEoMCwgMCwgMCwgMC4wMikiLz48cGF0aCBkPSJNMCAwaDQwdjFIMHpNMCAzOWg0MHYxSDB6IiBmaWxsPSJyZ2JhKDAsIDAsIDAsIDAuMDIpIi8+PC9zdmc+')] opacity-60 -z-10 mix-blend-overlay" />
          
          <div className="container mx-auto text-center max-w-4xl animate-fade-in relative z-10 w-full">
            <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-white/60 dark:bg-card/60 text-primary mb-6 text-sm font-bold border border-primary/20 shadow-[0_4px_20px_rgba(234,179,8,0.15)] backdrop-blur-xl">
              <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse"></span>
              Banana Classification System
            </div>
            <h1 className="text-4xl sm:text-5xl md:text-6xl lg:text-7xl font-extrabold tracking-tight mb-6 text-foreground drop-shadow-sm leading-[1.15]">
              Smarter Classification with <br className="hidden sm:block" />
              <span className="text-transparent bg-clip-text bg-linear-to-r from-primary via-yellow-500 to-orange-500 pb-1 drop-shadow-md inline-block mt-1">BananaVision</span>
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground mb-10 max-w-3xl mx-auto leading-relaxed">
              An AI-powered banana classification system built for Micro, Small, and Medium Enterprises (MSMEs). 
              Classify cultivar and ripeness in seconds, keep track of your stock, and reduce waste.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-5 w-full max-w-md mx-auto sm:max-w-none">
              <Button onClick={() => navigate("/login")} size="lg" className="h-14 px-10 shadow-[0_0_40px_-5px_rgba(234,179,8,0.6)] text-lg font-bold w-full sm:w-auto hover:shadow-[0_0_60px_-10px_rgba(234,179,8,0.8)] hover:-translate-y-1 transition-all duration-300">
                Access Dashboard <ChevronRight className="ml-2 w-5 h-5" />
              </Button>
              <Button onClick={() => scrollToSection("about")} variant="outline" size="lg" className="h-14 px-10 w-full sm:w-auto text-lg font-bold border-2 bg-white/50 backdrop-blur-sm hover:bg-primary/5 transition-all duration-300">
                Learn More
              </Button>
            </div>
          </div>
        </section>

        {/* About Section */}
        <section id="about" className="relative py-24 px-4 border-y border-border/50 overflow-hidden bg-linear-to-b from-primary/5 to-background">
          <div className="absolute left-0 right-0 top-0 h-px bg-linear-to-r from-transparent via-primary/20 to-transparent" />
          <div className="container mx-auto max-w-5xl relative z-10">
            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div className="space-y-6">
                <div className="inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold bg-banana-light text-banana-foreground">
                  Our Mission
                </div>
                <h2 className="text-3xl md:text-4xl font-bold">About BananaVision</h2>
                <p className="text-muted-foreground leading-relaxed">
                  BananaVision is an enterprise-grade AI solution built to solve real challenges faced by MSMEs in the banana supply chain. 
                </p>
                <p className="text-muted-foreground leading-relaxed">
                  Using AI and camera-based recognition, the system identifies the banana variety, determines how ripe it is, and estimates how long it will last — helping businesses speed up their scanning process and reduce product waste.
                </p>
              </div>
              <div className="relative perspective-1000">
                <div className="aspect-4/3 md:aspect-square rounded-[3rem] bg-linear-to-br from-white/90 to-white/40 dark:from-white/10 dark:to-white/5 backdrop-blur-2xl border border-white/60 dark:border-white/20 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.1)] flex items-center justify-center relative overflow-hidden group hover:rotate-3 transition-transform duration-700 ease-out">
                  <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-size-[24px_24px]" />
                  <div className="absolute -inset-2 bg-linear-to-tr from-primary/40 via-transparent to-orange-400/40 blur-2xl opacity-50 group-hover:opacity-100 transition-opacity duration-700" />
                  <div className="w-32 h-32 sm:w-48 sm:h-48 bg-white/90 dark:bg-black/50 backdrop-blur-2xl rounded-full flex items-center justify-center shadow-2xl border border-white/50 dark:border-white/10 relative z-10 transition-transform duration-700 group-hover:scale-110">
                    <img src="/bananavision-logo.svg" alt="BananaVision Logo" className="w-20 h-20 sm:w-28 sm:h-28 object-contain drop-shadow-xl" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Key Features Section */}
        <section id="features" className="relative py-24 px-4 overflow-hidden bg-linear-to-b from-background to-primary/5">
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full max-w-200 h-200 bg-primary/20 rounded-full blur-[120px] -z-10 pointer-events-none" />
          <div className="container mx-auto max-w-5xl text-center space-y-12 relative z-10">
            <div className="space-y-4">
              <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight">Key Features</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto text-lg">
                Everything your business needs to modernize banana handling and classification.
              </p>
            </div>
            
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-8 text-left relative z-10">
              {[
                { icon: ScanLine, title: "AI-Assisted Scanning", desc: "Recognizes banana varieties (Lakatan, Latundan, Saba), determines ripeness level, and automatically estimates shelf life." },
                { icon: Factory, title: "Operator Kiosk", desc: "A simple, touch-friendly screen where warehouse workers can quickly scan bananas one delivery at a time." },
                { icon: ShieldCheck, title: "Scan Review", desc: "Unsure classification results are easily flagged so a manager can double-check and correct them later." },
                { icon: PackageOpen, title: "Inventory Tracking", desc: "See how much stock you have by variety and ripeness, with alerts when items are about to spoil." },
                { icon: BarChart3, title: "Reports & Charts", desc: "View easy-to-read charts showing daily output, intake results, and worker performance." },
                { icon: ScrollText, title: "Full Scan History", desc: "Browse and search through every scan ever made, filtered by date, intake, or worker." },
              ].map((feature, i) => (
                <div key={i} className="group p-8 rounded-[2.5rem] bg-white/70 dark:bg-card/40 backdrop-blur-xl border border-white/60 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_20px_40px_rgb(234,179,8,0.1)] hover:-translate-y-2 transition-all duration-500 relative overflow-hidden flex flex-col">
                  {/* Subtle top glare */}
                  <div className="absolute top-0 left-0 right-0 h-25 bg-linear-to-b from-white/80 dark:from-white/5 to-transparent opacity-60 pointer-events-none" />
                  <div className="absolute inset-0 bg-linear-to-br from-primary/5 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none" />
                  
                  <div className="w-14 h-14 bg-linear-to-br from-primary/20 to-primary/5 border border-primary/20 rounded-[1rem] flex items-center justify-center mb-6 text-primary group-hover:scale-110 group-hover:shadow-lg group-hover:bg-primary group-hover:text-primary-foreground group-hover:border-primary transition-all duration-500 relative z-10">
                    <feature.icon className="w-7 h-7 drop-shadow-sm" />
                  </div>
                  <h3 className="text-2xl font-bold mb-3 group-hover:text-primary transition-colors relative z-10 tracking-tight">{feature.title}</h3>
                  <p className="text-muted-foreground leading-relaxed flex-1 relative z-10 font-medium">{feature.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Modules Section */}
        <section id="modules" className="relative py-24 px-4 border-y border-border/50 overflow-hidden bg-linear-to-b from-primary/5 to-background">
          <div className="absolute inset-0 bg-grid-black/[0.02] bg-size-[32px_32px] -z-10 pointer-events-none" />
          <div className="container mx-auto max-w-5xl space-y-12 relative z-10">
            <div className="text-center space-y-4">
              <h2 className="text-4xl md:text-5xl font-extrabold tracking-tight">System Modules</h2>
              <p className="text-muted-foreground max-w-2xl mx-auto text-lg">
                Different views for different roles — operators scan, managers oversee.
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-8 relative z-10">
              {[
                { 
                  num: "1", title: "Operator Kiosk", desc: "A focused scanning screen for warehouse workers.", 
                  items: ["Quick switch between operators using a PIN", "Multi-angle camera capture", "Choose which delivery source to scan for", "Accept good scans or flag for review", "See recent scan results instantly"]
                },
                { 
                  num: "2", title: "Operator Dashboard", desc: "A simplified dashboard showing only the operator's own work.", 
                  items: ["View your own scan results", "Personal scan history", "Charts showing your performance", "Check current stock & freshness alerts", "See if cameras are working"]
                },
                { 
                  num: "3", title: "Admin Dashboard", desc: "Complete visibility and control for managers.", 
                  items: ["Monitor all scans across the system", "Track inventory with freshness alerts", "View detailed charts and reports", "Review and correct scan results", "Manage users, suppliers & devices", "View activity history & system settings"]
                }
              ].map((module) => (
                <div key={module.num} className="group relative p-8 lg:p-10 rounded-[2.5rem] bg-white/80 dark:bg-card/40 backdrop-blur-2xl border border-white/60 dark:border-white/10 shadow-[0_8px_30px_rgb(0,0,0,0.04)] hover:shadow-[0_20px_40px_rgb(234,179,8,0.12)] hover:-translate-y-2 transition-all duration-500 overflow-hidden flex flex-col">
                  {/* Glassmorphic glare */}
                  <div className="absolute top-0 left-0 right-0 h-37.5 bg-linear-to-b from-white/70 dark:from-white/5 to-transparent opacity-80 pointer-events-none" />
                  
                  <div className="absolute -right-24 -top-24 w-48 h-48 bg-primary/10 rounded-full blur-3xl group-hover:bg-primary/25 transition-all duration-700" />
                  
                  <h3 className="text-2xl lg:text-3xl font-bold mb-4 flex items-center gap-4 relative z-10 tracking-tight">
                    <span className="w-12 h-12 rounded-[1rem] bg-linear-to-br from-primary/20 to-primary/5 border border-primary/20 flex items-center justify-center text-primary group-hover:bg-primary group-hover:text-primary-foreground group-hover:shadow-lg group-hover:scale-110 transition-all duration-500 text-lg font-black">
                      {module.num}
                    </span>
                    {module.title}
                  </h3>
                  <p className="text-base text-muted-foreground mb-8 relative z-10 flex-1 leading-relaxed font-medium">
                    {module.desc}
                  </p>
                  
                  <div className="w-full h-px bg-linear-to-r from-border/50 to-transparent mb-6 relative z-10" />
                  
                  <ul className="space-y-4 relative z-10">
                    {module.items.map((item, i) => (
                      <li key={i} className="flex items-start gap-3 text-muted-foreground text-sm group-hover:text-foreground/90 transition-colors">
                        <CheckCircle2 className="w-5 h-5 text-primary shrink-0 mt-0.5 drop-shadow-sm" /> 
                        <span className="leading-snug">{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* FAQs Section */}
        <section id="faqs" className="relative py-24 px-4 overflow-hidden bg-linear-to-b from-background to-primary/5">
          <div className="container mx-auto max-w-3xl space-y-12 relative z-10">
            <div className="text-center space-y-4">
              <h2 className="text-3xl md:text-4xl font-bold">Frequently Asked Questions</h2>
            </div>
            
            <Accordion type="single" collapsible className="w-full">
              <AccordionItem value="item-1">
                <AccordionTrigger className="text-left text-lg">Who is this system built for?</AccordionTrigger>
                <AccordionContent className="text-muted-foreground h-auto">
                  BananaVision is made for small to medium-sized businesses that handle banana packaging and distribution. It helps workers classify bananas faster and gives managers a clear picture of their inventory.
                </AccordionContent>
              </AccordionItem>
              <AccordionItem value="item-2">
                <AccordionTrigger className="text-left text-lg">Does it need an internet connection?</AccordionTrigger>
                <AccordionContent className="text-muted-foreground h-auto">
                  No. The entire system runs on a local mini PC that hosts both the frontend and backend. Devices like tablets or computers simply connect to the mini PC through a local network (LAN or hotspot) — no internet required.
                </AccordionContent>
              </AccordionItem>
              <AccordionItem value="item-3">
                <AccordionTrigger className="text-left text-lg">What hardware is needed?</AccordionTrigger>
                <AccordionContent className="text-muted-foreground h-auto">
                  The scanning station uses a mini PC that runs the entire system. It connects to external webcams for capturing banana images and an external monitor that displays the Kiosk interface for the operator. Other devices can access the dashboard by connecting to the mini PC over the local network.
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </div>
        </section>

        {/* Contact Support Section */}
        <section id="contact" className="relative py-24 px-4 border-t border-border/50 text-center overflow-hidden bg-linear-to-b from-primary/5 to-primary/10">
          <div className="absolute bottom-0 left-0 right-0 h-px bg-linear-to-r from-transparent via-primary/30 to-transparent" />
          <div className="container mx-auto max-w-2xl space-y-8 relative z-10">
            <div className="w-16 h-16 bg-primary/10 rounded-2xl mx-auto flex items-center justify-center text-primary">
              <Mail className="w-8 h-8" />
            </div>
            <h2 className="text-3xl md:text-4xl font-bold">Need Help?</h2>
            <p className="text-muted-foreground">
              Have questions about setting up BananaVision for your business? We're here to help.
            </p>
            <Button 
              size="lg" 
              className="h-12 px-8"
              onClick={() => window.location.href = "mailto:support@bananavision.com"}
            >
              Contact Support Team
            </Button>
          </div>
        </section>
      </main>

      <footer className="py-8 border-t bg-background text-center text-muted-foreground text-sm">
        <p>© {new Date().getFullYear()} BananaVision. All rights reserved.</p>
      </footer>
    </div>
  )
}
