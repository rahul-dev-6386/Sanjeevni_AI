"use client"

import { useState, useEffect } from "react"
import { usePathname } from "next/navigation"
import { Sidebar } from "./sidebar"
import { TopHeader } from "./top-header"
import { cn } from "@/lib/utils"
import { motion, AnimatePresence } from "framer-motion"

const publicPaths = ["/", "/login", "/register"]
const noHeaderPaths = ["/chat"]

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  const isPublic = publicPaths.includes(pathname)
  const showHeader = !noHeaderPaths.includes(pathname)

  if (!mounted) {
    return <div className="min-h-screen bg-[#0B0F1A]">{children}</div>
  }

  if (isPublic) {
    return <>{children}</>
  }

  return (
    <div className="h-screen bg-[#0B0F1A] overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
      <div
        className={cn(
          "transition-all duration-300 h-full flex flex-col",
          collapsed ? "ml-[72px]" : "ml-sidebar"
        )}
      >
        {showHeader && <TopHeader />}
        <AnimatePresence mode="wait">
          <motion.main
            key={pathname}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="flex-1 min-h-0 overflow-y-auto"
          >
            {children}
          </motion.main>
        </AnimatePresence>
      </div>
    </div>
  )
}
