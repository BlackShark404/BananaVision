import { useState, useEffect } from "react"

export function useLocalStorage<T>(key: string, initialValue: T | (() => T)) {
  // Pass initial state function to useState so logic is only executed once
  const [storedValue, setStoredValue] = useState<T>(() => {
    if (typeof window === "undefined") {
      return initialValue instanceof Function ? initialValue() : initialValue
    }
    
    try {
      const item = window.localStorage.getItem(key)
      if (item) {
        return JSON.parse(item)
      }
    } catch (error) {
      console.warn(`Error reading localStorage key "${key}":`, error)
    }
    
    return initialValue instanceof Function ? initialValue() : initialValue
  })

  // Update localStorage whenever the state changes
  useEffect(() => {
    if (typeof window !== "undefined") {
      try {
        if (storedValue === null || storedValue === undefined) {
          window.localStorage.removeItem(key)
        } else {
          window.localStorage.setItem(key, JSON.stringify(storedValue))
        }
      } catch (error) {
        console.warn(`Error setting localStorage key "${key}":`, error)
      }
    }
  }, [key, storedValue])

  return [storedValue, setStoredValue] as const
}
