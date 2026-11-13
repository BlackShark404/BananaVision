// The real auth module. The harness aliases "@/context/AuthContext" to a file in tests/;
// this relative re-export lets a fixture run the real AuthProvider and stored session.
export * from "../src/context/AuthContext"
