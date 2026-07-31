"use client"

import React, { createContext, useContext, useState, useEffect, useCallback } from "react"
import { getCookie, removeCookie, setAuthTokensInMemory } from "@/lib/utils"

export interface User {
  id: number
  email: string
  full_name: string
  avatar_url: string | null
  role: string
}

export interface AuthTokens {
  access_token: string
  refresh_token: string
}

interface AuthContextType {
  user: User | null
  tokens: AuthTokens | null
  login: (tokens: AuthTokens, user: User) => void
  logout: () => void
  isAuthenticated: boolean
  isLoading: boolean
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

const API_URL = process.env.NEXT_PUBLIC_API_URL || "/api"

function persistTokens(t: AuthTokens) {
  document.cookie = `access_token=${t.access_token}; path=/; SameSite=Lax`
  document.cookie = `refresh_token=${t.refresh_token}; path=/; SameSite=Lax`
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [tokens, setTokens] = useState<AuthTokens | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // On mount, try to restore session from cookies
  useEffect(() => {
    const initAuth = async () => {
      try {
        const access = getCookie("access_token")
        const refresh = getCookie("refresh_token")
        if (access && refresh) {
          const initialTokens = { access_token: access, refresh_token: refresh }
          setTokens(initialTokens)
          setAuthTokensInMemory(initialTokens)

          // Validate token by fetching /me
          const res = await fetch(`${API_URL}/auth/me`, {
            headers: { Authorization: `Bearer ${access}` },
          })
          if (res.ok) {
            const data = await res.json()
            setUser(data.user)
            setIsLoading(false)
            return
          }

          // Token expired — try refresh
          const refreshRes = await fetch(`${API_URL}/auth/refresh`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refresh }),
          })
          if (refreshRes.ok) {
            const data = await refreshRes.json()
            const newTokens = { access_token: data.access_token, refresh_token: data.refresh_token }
            setTokens(newTokens)
            setUser(data.user)
            persistTokens(newTokens)
          }
        }
      } catch {
        // Session invalid — stay logged out
      }
      setIsLoading(false)
    }
    initAuth()
  }, [])

  const login = useCallback((newTokens: AuthTokens, newUser: User) => {
    setTokens(newTokens)
    setUser(newUser)
    setAuthTokensInMemory(newTokens)
    persistTokens(newTokens)
  }, [])

  const logout = useCallback(async () => {
    try {
      const refresh = tokens?.refresh_token || getCookie("refresh_token")
      if (refresh) {
        await fetch(`${API_URL}/auth/logout`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        })
      }
    } catch {
      // Best-effort logout
    }
    removeCookie("access_token", "/")
    removeCookie("refresh_token", "/")
    setAuthTokensInMemory(null)
    setTokens(null)
    setUser(null)
    window.location.href = "/"
  }, [tokens])

  return (
    <AuthContext.Provider
      value={{
        user,
        tokens,
        login,
        logout,
        isAuthenticated: !!user && !!tokens,
        isLoading,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider")
  }
  return context
}
