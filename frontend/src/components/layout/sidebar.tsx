"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  Bot,
  BarChart3,
  FileText,
  Pill,
  Calendar,
  BookOpen,
  Settings,
  LogOut,
  ChevronLeft,
  Activity,
  Sun,
  TrendingUp,
  Search,
} from "lucide-react"
import { useAuth } from "@/store/auth-context"
import { motion } from "framer-motion"
import { useState } from "react"

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "AI Chat", icon: Bot },
  { href: "/search", label: "Smart Search", icon: Search },
  { href: "/metrics", label: "Health Metrics", icon: BarChart3 },
  { href: "/analytics", label: "Health Trends", icon: TrendingUp },
  { href: "/reports", label: "Medical Reports", icon: FileText },
  { href: "/medications", label: "Medications", icon: Pill },
  { href: "/timeline", label: "Timeline", icon: Calendar },
  { href: "/library", label: "Medical Library", icon: BookOpen },
  { href: "/drugs", label: "Drug Info", icon: Pill },
  { href: "/routines", label: "Daily Plans", icon: Sun },
]

const bottomItems = [
  { href: "/settings", label: "Settings", icon: Settings },
]

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname()
  const { logout, user } = useAuth()

  return (
    <motion.aside
      initial={false}
      animate={{ width: collapsed ? 72 : 260 }}
      className={cn(
        "fixed left-0 top-0 bottom-0 z-40",
        "bg-[#0B0F1A] border-r border-[#2B364A]",
        "flex flex-col overflow-hidden"
      )}
    >
      {/* Header */}
      <div className="flex items-center h-16 px-4 border-b border-[#2B364A] shrink-0">
        <Link href="/dashboard" className="flex items-center gap-3 min-w-0">
          <div className="w-8 h-8 rounded-lg bg-[#0EA5A9] flex items-center justify-center shrink-0">
            <Activity className="h-4.5 w-4.5 text-white" />
          </div>
          {!collapsed && (
            <span className="font-bold text-base text-[#EDF2F7] tracking-tight">
              Sanjeevni AI
            </span>
          )}
        </Link>
        <button
          onClick={onToggle}
          className={cn("btn-clinical-icon ml-auto", collapsed && "mx-auto")}
        >
          <ChevronLeft className={cn("h-4 w-4 transition-transform duration-300", collapsed && "rotate-180")} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto overflow-x-hidden">
        {navItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== "/" && pathname.startsWith(item.href))
          return (
            <Link key={item.href} href={item.href}>
              <div
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                  isActive
                    ? "bg-[#0EA5A9]/10 text-[#0EA5A9]"
                    : "text-[#8B9BB5] hover:text-[#EDF2F7] hover:bg-[#181E2E]",
                  collapsed && "justify-center px-2"
                )}
              >
                <item.icon className="h-5 w-5 shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </div>
            </Link>
          )
        })}
      </nav>

      {/* Bottom section */}
      <div className={cn("px-2 py-2 border-t border-[#2B364A] space-y-0.5", collapsed && "flex flex-col items-center")}>
        {bottomItems.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link key={item.href} href={item.href}>
              <div
                className={cn(
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200",
                  isActive
                    ? "bg-[#0EA5A9]/10 text-[#0EA5A9]"
                    : "text-[#8B9BB5] hover:text-[#EDF2F7] hover:bg-[#181E2E]",
                  collapsed && "justify-center px-2"
                )}
              >
                <item.icon className="h-5 w-5 shrink-0" />
                {!collapsed && <span className="truncate">{item.label}</span>}
              </div>
            </Link>
          )
        })}
        <button
          onClick={logout}
          className={cn(
            "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 w-full",
            "text-[#8B9BB5] hover:text-red-400 hover:bg-red-500/10",
            collapsed && "justify-center px-2"
          )}
        >
          <LogOut className="h-5 w-5 shrink-0" />
          {!collapsed && <span className="truncate">Sign Out</span>}
        </button>
      </div>

      {/* User info */}
      {!collapsed && (
        <div className="px-4 py-3 border-t border-[#2B364A]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-[#0EA5A9] flex items-center justify-center text-xs font-bold text-white">
              {(user?.full_name || "U").charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-[#EDF2F7] truncate">{user?.full_name || "Guest User"}</p>
              <p className="text-[10px] text-[#8B9BB5] truncate">{user?.email || ""}</p>
            </div>
          </div>
        </div>
      )}
    </motion.aside>
  )
}
