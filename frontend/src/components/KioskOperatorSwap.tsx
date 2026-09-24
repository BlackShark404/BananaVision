import { useState, useCallback, useEffect } from "react"
import { useAuth } from "@/context/AuthContext"
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import { Delete, ArrowLeft, ShieldCheck, KeyRound, Fingerprint, CheckCircle2 } from "lucide-react"
import { toast } from "sonner"

// ── Types ──────────────────────────────────────────────────────────────────

interface Operator {
  id: string
  username: string
  fullName: string
  role: string
  status: string
  avatar?: string
}

type SwapPhase = "select" | "pin" | "new-pin" | "confirm-pin"

interface KioskOperatorSwapProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** List of active operators available for selection */
  operators: Operator[]
  /** Currently active operator id, if any */
  currentOperatorId: string | null
  /** Called when operator swap is successful */
  onSwapSuccess: (operatorId: string) => void
}

// ── Constants ──────────────────────────────────────────────────────────────

const PIN_LENGTH = 4

const KEYPAD_KEYS = [
  ["1", "2", "3"],
  ["4", "5", "6"],
  ["7", "8", "9"],
  ["", "0", "backspace"],
] as const

// ── Helper: Initials ───────────────────────────────────────────────────────

function getInitials(name: string) {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
}

// ── PIN Dot Display ────────────────────────────────────────────────────────

function PinDots({ length, filled, shake }: { length: number; filled: number; shake: boolean }) {
  return (
    <div className={`flex items-center justify-center gap-3.5 ${shake ? "animate-shake" : ""}`}>
      {Array.from({ length }).map((_, i) => (
        <div
          key={i}
          className={`
            w-4 h-4 rounded-full border-2 transition-all duration-200
            ${i < filled
              ? "bg-primary border-primary scale-110 shadow-sm shadow-primary/30"
              : "border-muted-foreground/30 bg-transparent"
            }
          `}
          style={{
            transitionDelay: i < filled ? `${i * 40}ms` : "0ms",
          }}
        />
      ))}
    </div>
  )
}

// ── Touch Keypad ───────────────────────────────────────────────────────────

function TouchKeypad({
  onKeyPress,
  disabled,
}: {
  onKeyPress: (key: string) => void
  disabled?: boolean
}) {
  return (
    <div className="grid grid-cols-3 gap-2.5 w-full max-w-[280px] mx-auto">
      {KEYPAD_KEYS.flat().map((key, idx) => {
        if (key === "") {
          return <div key={`empty-${idx}`} className="aspect-square" />
        }

        if (key === "backspace") {
          return (
            <button
              key="backspace"
              type="button"
              disabled={disabled}
              onClick={() => onKeyPress("backspace")}
              className="
                aspect-square rounded-2xl
                flex items-center justify-center
                bg-muted/60 hover:bg-destructive/10 active:bg-destructive/20
                border border-border hover:border-destructive/30
                text-muted-foreground hover:text-destructive
                transition-all duration-150
                active:scale-[0.92]
                disabled:opacity-40 disabled:pointer-events-none
                touch-manipulation select-none
              "
            >
              <Delete className="w-5 h-5" />
            </button>
          )
        }

        return (
          <button
            key={key}
            type="button"
            disabled={disabled}
            onClick={() => onKeyPress(key)}
            className="
              aspect-square rounded-2xl
              flex items-center justify-center
              text-2xl font-semibold
              bg-card hover:bg-accent active:bg-primary/10
              border border-border hover:border-primary/30
              text-foreground
              transition-all duration-150
              active:scale-[0.92] active:border-primary/50
              shadow-sm hover:shadow-md
              disabled:opacity-40 disabled:pointer-events-none
              touch-manipulation select-none
            "
          >
            {key}
          </button>
        )
      })}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function KioskOperatorSwap({
  open,
  onOpenChange,
  operators,
  currentOperatorId,
  onSwapSuccess,
}: KioskOperatorSwapProps) {
  const { user, switchOperator, changePinAndLogin } = useAuth()

  // ── Local State ──────────────────────────────────────────────────────────

  const [phase, setPhase] = useState<SwapPhase>("select")
  const [targetId, setTargetId] = useState<string | null>(null)
  const [pin, setPin] = useState("")
  const [newPin, setNewPin] = useState("")
  const [confirmPin, setConfirmPin] = useState("")
  const [shake, setShake] = useState(false)
  const [isProcessing, setIsProcessing] = useState(false)
  const [pinChangeMessage, setPinChangeMessage] = useState("Please set your new secure 4-digit PIN.")

  const targetOperator = operators.find((o) => o.id === targetId) ?? null

  // ── Reset state when dialog closes / opens ───────────────────────────────

  useEffect(() => {
    if (!open) {
      // Delay reset to let close animation complete
      const t = setTimeout(() => {
        setPhase("select")
        setTargetId(null)
        setPin("")
        setNewPin("")
        setConfirmPin("")
        setShake(false)
        setIsProcessing(false)
      }, 200)
      return () => clearTimeout(t)
    }
  }, [open])

  // ── Shake helper ─────────────────────────────────────────────────────────

  const triggerShake = useCallback(() => {
    setShake(true)
    setTimeout(() => setShake(false), 500)
  }, [])

  // ── PIN Entry Handler ────────────────────────────────────────────────────

  const handlePinVerify = useCallback(
    async (fullPin: string) => {
      if (!targetOperator) return
      setIsProcessing(true)

      try {
        const result = await switchOperator(targetOperator.username, fullPin)

        if (result === "success") {
          toast.success(`Swapped to ${targetOperator.fullName}`)
          onSwapSuccess(targetOperator.id)
          onOpenChange(false)
        } else if (
          result === "requires_pin_change" ||
          result === "requires_pin_change_new_account" ||
          result === "requires_pin_change_reset"
        ) {
          if (result === "requires_pin_change_new_account") {
            setPinChangeMessage("Welcome! An Admin created this account. Please set your new secure PIN.")
          } else if (result === "requires_pin_change_reset") {
            setPinChangeMessage("Welcome back! Your PIN was recently reset. Please set your new secure PIN.")
          } else {
            setPinChangeMessage("Please set a new secure 4-digit PIN to continue.")
          }
          setPhase("new-pin")
          setPin("")
        } else if (result === "inactive") {
          toast.error("Account Inactive", {
            description: "Your account is inactive. Please contact an administrator.",
          })
          setPin("")
          triggerShake()
        } else {
          toast.error("Invalid PIN code")
          setPin("")
          triggerShake()
        }
      } finally {
        setIsProcessing(false)
      }
    },
    [targetOperator, switchOperator, onSwapSuccess, onOpenChange, triggerShake]
  )

  // ── New PIN Confirm Handler ──────────────────────────────────────────────

  const handleNewPinConfirm = useCallback(
    async (confirmed: string) => {
      if (!targetOperator) return

      if (newPin !== confirmed) {
        toast.error("PINs do not match. Try again.")
        setNewPin("")
        setConfirmPin("")
        setPhase("new-pin")
        triggerShake()
        return
      }

      setIsProcessing(true)
      try {
        const success = await changePinAndLogin(targetOperator.username, confirmed)
        if (success) {
          toast.success(`PIN updated and swapped to ${targetOperator.fullName}`)
          onSwapSuccess(targetOperator.id)
          onOpenChange(false)
        } else {
          toast.error("Failed to update PIN. Try again.")
          setNewPin("")
          setConfirmPin("")
          setPhase("new-pin")
        }
      } finally {
        setIsProcessing(false)
      }
    },
    [targetOperator, newPin, changePinAndLogin, onSwapSuccess, onOpenChange, triggerShake]
  )

  // ── Key Press Router ─────────────────────────────────────────────────────

  const handleKeyPress = useCallback(
    (key: string) => {
      if (isProcessing) return

      if (phase === "pin") {
        if (key === "backspace") {
          setPin((prev) => prev.slice(0, -1))
        } else if (pin.length < PIN_LENGTH) {
          const next = pin + key
          setPin(next)
          if (next.length === PIN_LENGTH) {
            // Small delay so the user sees the last dot fill
            setTimeout(() => handlePinVerify(next), 200)
          }
        }
      } else if (phase === "new-pin") {
        if (key === "backspace") {
          setNewPin((prev) => prev.slice(0, -1))
        } else if (newPin.length < PIN_LENGTH) {
          const next = newPin + key
          setNewPin(next)
          if (next.length === PIN_LENGTH) {
            setTimeout(() => {
              setPhase("confirm-pin")
            }, 250)
          }
        }
      } else if (phase === "confirm-pin") {
        if (key === "backspace") {
          setConfirmPin((prev) => prev.slice(0, -1))
        } else if (confirmPin.length < PIN_LENGTH) {
          const next = confirmPin + key
          setConfirmPin(next)
          if (next.length === PIN_LENGTH) {
            setTimeout(() => handleNewPinConfirm(next), 200)
          }
        }
      }
    },
    [phase, pin, newPin, confirmPin, isProcessing, handlePinVerify, handleNewPinConfirm]
  )

  // ── Prevent closing when no operator selected yet ────────────────────────

  const handleOpenChange = useCallback(
    (nextOpen: boolean) => {
      if (!nextOpen && !currentOperatorId) return // Can't dismiss without an operator
      onOpenChange(nextOpen)
    },
    [currentOperatorId, onOpenChange]
  )

  // ── Go Back ──────────────────────────────────────────────────────────────

  const handleBack = useCallback(() => {
    setTargetId(null)
    setPin("")
    setNewPin("")
    setConfirmPin("")
    setShake(false)
    setPhase("select")
  }, [])

  // ── Render ───────────────────────────────────────────────────────────────

  const renderTitle = () => {
    if (phase === "select") {
      return currentOperatorId ? "Switch Operator" : "Select Operator to Begin"
    }
    if (phase === "pin") return "Enter PIN"
    if (phase === "new-pin") return "Create New Kiosk PIN"
    return "Confirm New PIN"
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="sm:max-w-md rounded-2xl p-0 overflow-hidden"
        showCloseButton={!!currentOperatorId}
      >
        {/* ─── Header ─────────────────────────────────────────────── */}
        <DialogHeader className="px-6 pt-6 pb-2">
          <div className="flex items-center gap-3">
            {phase !== "select" && (
              <button
                onClick={handleBack}
                className="
                  w-8 h-8 rounded-xl
                  flex items-center justify-center
                  bg-muted/60 hover:bg-muted
                  border border-border
                  text-muted-foreground hover:text-foreground
                  transition-colors
                  touch-manipulation
                "
              >
                <ArrowLeft className="w-4 h-4" />
              </button>
            )}
            <div>
              <DialogTitle className="text-lg">{renderTitle()}</DialogTitle>
              {phase === "select" && !currentOperatorId && (
                <DialogDescription className="text-sm text-muted-foreground mt-0.5">
                  Please select an operator and authenticate to use the kiosk.
                </DialogDescription>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* ─── Phase: Select Operator ─────────────────────────────── */}
        {phase === "select" && (
          <div className="px-6 pb-6 pt-2">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {operators.map((op) => (
                <button
                  key={op.id}
                  onClick={() => {
                    setTargetId(op.id)
                    setPhase("pin")
                  }}
                  className={`
                    flex flex-col items-center gap-2.5 p-4 rounded-2xl border-2
                    transition-all duration-200 touch-manipulation select-none
                    active:scale-[0.96]
                    ${
                      op.id === user?.id
                        ? "bg-primary/8 border-primary/40 shadow-sm shadow-primary/10"
                        : "bg-card border-border hover:bg-accent hover:border-primary/20 hover:shadow-sm"
                    }
                  `}
                >
                  <Avatar className="w-14 h-14 border-2 border-background shadow-sm">
                    {op.avatar ? (
                      <AvatarImage src={op.avatar} className="object-cover" />
                    ) : null}
                    <AvatarFallback className="bg-primary/10 text-primary font-bold text-base">
                      {getInitials(op.fullName)}
                    </AvatarFallback>
                  </Avatar>
                  <div className="text-center w-full">
                    <p className="text-xs font-semibold truncate px-1">{op.fullName}</p>
                    <p className="text-[10px] text-muted-foreground">{op.role}</p>
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* ─── Phase: PIN Entry ──────────────────────────────────── */}
        {phase === "pin" && targetOperator && (
          <div className="px-6 pb-6 pt-2 space-y-5">
            {/* Operator card */}
            <div className="flex items-center gap-3 p-3 bg-muted/40 rounded-xl border border-border">
              <Avatar className="w-10 h-10">
                {targetOperator.avatar ? (
                  <AvatarImage src={targetOperator.avatar} className="object-cover" />
                ) : null}
                <AvatarFallback className="bg-primary/10 text-primary font-bold text-sm">
                  {getInitials(targetOperator.fullName)}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{targetOperator.fullName}</p>
                <p className="text-xs text-muted-foreground flex items-center gap-1">
                  <KeyRound className="w-3 h-3" />
                  Enter your 4-digit PIN
                </p>
              </div>
            </div>

            {/* PIN dots */}
            <PinDots length={PIN_LENGTH} filled={pin.length} shake={shake} />

            {/* Keypad */}
            <TouchKeypad onKeyPress={handleKeyPress} disabled={isProcessing} />

            {/* Processing indicator */}
            {isProcessing && (
              <div className="flex items-center justify-center gap-2 text-sm text-primary animate-pulse">
                <Fingerprint className="w-4 h-4" />
                Verifying...
              </div>
            )}
          </div>
        )}

        {/* ─── Phase: New PIN ────────────────────────────────────── */}
        {phase === "new-pin" && targetOperator && (
          <div className="px-6 pb-6 pt-2 space-y-5">
            {/* Message card */}
            <div className="flex items-center gap-3 p-3 bg-amber-500/8 rounded-xl border border-amber-500/20">
              <Avatar className="w-10 h-10">
                <AvatarFallback className="bg-amber-500/15 text-amber-600 font-bold text-sm">
                  {getInitials(targetOperator.fullName)}
                </AvatarFallback>
              </Avatar>
              <div className="min-w-0">
                <p className="text-sm font-semibold truncate">{targetOperator.fullName}</p>
                <p className="text-[11px] text-amber-600 dark:text-amber-400 font-medium leading-tight">
                  {pinChangeMessage}
                </p>
              </div>
            </div>

            {/* Label */}
            <p className="text-xs font-semibold text-muted-foreground uppercase text-center tracking-wide">
              Create a new 4-digit PIN
            </p>

            {/* PIN dots */}
            <PinDots length={PIN_LENGTH} filled={newPin.length} shake={shake} />

            {/* Keypad */}
            <TouchKeypad onKeyPress={handleKeyPress} disabled={isProcessing} />
          </div>
        )}

        {/* ─── Phase: Confirm New PIN ────────────────────────────── */}
        {phase === "confirm-pin" && targetOperator && (
          <div className="px-6 pb-6 pt-2 space-y-5">
            {/* Success indicator for first PIN */}
            <div className="flex items-center gap-3 p-3 bg-emerald-500/8 rounded-xl border border-emerald-500/20">
              <div className="w-10 h-10 rounded-full bg-emerald-500/15 flex items-center justify-center shrink-0">
                <CheckCircle2 className="w-5 h-5 text-emerald-600" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold">PIN Created</p>
                <p className="text-[11px] text-emerald-600 dark:text-emerald-400 font-medium">
                  Now re-enter to confirm.
                </p>
              </div>
            </div>

            {/* Label */}
            <p className="text-xs font-semibold text-muted-foreground uppercase text-center tracking-wide">
              Confirm your new PIN
            </p>

            {/* PIN dots */}
            <PinDots length={PIN_LENGTH} filled={confirmPin.length} shake={shake} />

            {/* Keypad */}
            <TouchKeypad onKeyPress={handleKeyPress} disabled={isProcessing} />

            {/* Processing indicator */}
            {isProcessing && (
              <div className="flex items-center justify-center gap-2 text-sm text-primary animate-pulse">
                <ShieldCheck className="w-4 h-4" />
                Updating PIN...
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
