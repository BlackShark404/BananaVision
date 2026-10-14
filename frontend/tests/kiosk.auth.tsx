const user = { id: "operator-1", username: "fixture", fullName: "Fixture Operator", role: "Operator" as const }

/** Isolated auth boundary: exercise the real kiosk chooser without real credentials. */
export function useAuth() {
  return {
    user,
    switchOperator: async () => "success",
    setupPinAndLogin: async () => true,
    updateAuthUser: () => {},
  }
}
