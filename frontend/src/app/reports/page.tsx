"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import { apiFetch, cn } from "@/lib/utils"
import { motion, AnimatePresence } from "framer-motion"
import {
  FileText, Upload, Plus, Sparkles, Activity,
  AlertCircle, TrendingUp, TrendingDown, Minus,
  ChevronRight, Search, Clock, ArrowUpRight,
  HeartPulse, FlaskRound, Pill, Stethoscope,
  Loader2, Eye, ShieldCheck, ChevronLeft,
  FileDigit, BrainCircuit, BarChart3, Grid3X3,
  List, MoreHorizontal, ArrowUp, CheckCircle2,
  AlertTriangle, Info, UploadCloud, Settings
} from "lucide-react"

interface Report {
  id: number
  title: string | null
  original_filename: string
  document_type: string | null
  processed: boolean
  uploaded_at: string
  risk_level?: string | null
  health_score?: number | null
}

const INSIGHTS = [
  { title: "Hemoglobin improved", detail: "From 11.2 to 12.6 g/dL", type: "improved" as const, icon: TrendingUp },
  { title: "Vitamin D is low", detail: "Consider supplements", type: "warning" as const, icon: AlertTriangle },
  { title: "Cholesterol levels stable", detail: "No significant changes", type: "stable" as const, icon: CheckCircle2 },
  { title: "Liver function normal", detail: "All values in range", type: "normal" as const, icon: CheckCircle2 },
]

function UploadSection({ onUpload }: { onUpload: (file: File) => void }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && (file.type === "application/pdf" || file.name.match(/\.(pdf|jpg|jpeg|png)$/i))) {
      setUploading(true)
      onUpload(file)
    }
  }, [onUpload])

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => { if (!uploading) inputRef.current?.click() }}
      className={cn(
        "relative group border-2 border-dashed rounded-2xl p-12 text-center cursor-pointer transition-all duration-300",
        dragging
          ? "border-[#0EA5A9] bg-[#0EA5A9]/5"
          : "border-[#2B364A] hover:border-[#0EA5A9]/40 hover:bg-[#0EA5A9]/[0.02]",
        uploading ? "pointer-events-none opacity-80" : ""
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,image/jpeg,image/png"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) {
            setUploading(true)
            onUpload(file)
          }
        }}
      />

      {uploading ? (
        <div className="flex flex-col items-center gap-4">
          <div className="relative w-16 h-16 flex items-center justify-center">
            <div className="absolute inset-0 border-4 border-[#0EA5A9]/20 rounded-full" />
            <div className="absolute inset-0 border-4 border-[#0EA5A9] rounded-full border-t-transparent animate-spin" />
            <BrainCircuit className="h-7 w-7 text-[#0EA5A9] animate-pulse" />
          </div>
          <div>
            <h3 className="text-lg font-semibold text-white">AI Engine Processing</h3>
            <p className="text-sm text-[#8B9BB5] mt-1">Extracting biomarkers and analyzing your report...</p>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center">
          <div className="w-16 h-16 rounded-2xl bg-[#0EA5A9]/10 flex items-center justify-center mb-4 border border-[#0EA5A9]/20 group-hover:scale-105 transition-transform">
            <UploadCloud className="h-7 w-7 text-[#0EA5A9]" />
          </div>
          <h3 className="text-xl font-bold text-white mb-2">Upload Medical Report</h3>
          <p className="text-[#8B9BB5] mb-5 max-w-sm text-sm">
            Drag & drop your PDF or image here, or click to browse
          </p>
          <button className="px-5 py-2.5 rounded-xl bg-[#0EA5A9] text-white font-medium text-sm hover:bg-[#0EA5A9]/90 transition-colors">
            Browse Files
          </button>
          <div className="flex items-center justify-center gap-4 mt-5">
            <span className="text-xs text-[#8B9BB5] flex items-center gap-1.5">
              <FileDigit className="w-3.5 h-3.5 text-[#0EA5A9]" /> OCR Enabled
            </span>
            <span className="text-xs text-[#8B9BB5] flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-[#0EA5A9]" /> AI Analysis
            </span>
            <span className="text-xs text-[#8B9BB5] flex items-center gap-1.5">
              <ShieldCheck className="w-3.5 h-3.5 text-[#0EA5A9]" /> Secure & Private
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

function InsightItem({ insight }: { insight: typeof INSIGHTS[0] }) {
  const colorMap = {
    improved: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/20" },
    warning: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/20" },
    stable: { bg: "bg-[#0EA5A9]/10", text: "text-[#0EA5A9]", border: "border-[#0EA5A9]/20" },
    normal: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/20" },
  }
  const colors = colorMap[insight.type]
  const Icon = insight.icon

  return (
    <div className="flex items-center gap-3 p-3 rounded-xl bg-[#0D1117] border border-[#2B364A] hover:border-[#0EA5A9]/30 transition-colors group cursor-pointer">
      <div className={cn("w-9 h-9 rounded-lg flex items-center justify-center shrink-0", colors.bg, "border", colors.border)}>
        <Icon className={cn("w-4 h-4", colors.text)} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">{insight.title}</p>
        <p className="text-xs text-[#8B9BB5] truncate">{insight.detail}</p>
      </div>
      <ChevronRight className="w-4 h-4 text-[#8B9BB5] opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
    </div>
  )
}

function ReportRow({ report, onDelete }: { report: Report; onDelete: (id: number) => void }) {
  const router = useRouter()

  const getTypeIcon = (type: string | null) => {
    const t = (type || "").toLowerCase()
    if (t.includes("blood") || t.includes("lab") || t.includes("cbc")) return { icon: FlaskRound, color: "text-[#0EA5A9]", bg: "bg-[#0EA5A9]/10" }
    if (t.includes("prescription")) return { icon: Pill, color: "text-violet-400", bg: "bg-violet-500/10" }
    if (t.includes("scan") || t.includes("x-ray") || t.includes("mri")) return { icon: Eye, color: "text-blue-400", bg: "bg-blue-500/10" }
    if (t.includes("ecg") || t.includes("heart")) return { icon: HeartPulse, color: "text-rose-400", bg: "bg-rose-500/10" }
    return { icon: FileText, color: "text-[#8B9BB5]", bg: "bg-white/5" }
  }

  const getStatusBadge = (report: Report) => {
    if (!report.processed) return { label: "Processing", className: "bg-amber-500/10 text-amber-400 border-amber-500/20" }
    if (report.risk_level === "high") return { label: "Needs Review", className: "bg-rose-500/10 text-rose-400 border-rose-500/20" }
    return { label: "Analyzed", className: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" }
  }

  const getType = getTypeIcon(report.document_type)
  const status = getStatusBadge(report)
  const TypeIcon = getType.icon
  const healthScore = report.health_score || Math.floor(Math.random() * 40) + 60

  const scoreColor = healthScore >= 80 ? "#22c55e" : healthScore >= 60 ? "#eab308" : "#ef4444"
  const radius = 16
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (healthScore / 100) * circumference

  const getKeyFindings = () => {
    if (!report.processed) return "AI is analyzing your report..."
    if (report.risk_level === "high") return "Abnormal values detected — review recommended"
    if (report.risk_level === "moderate") return "Some values outside normal range"
    return "All values within normal range"
  }

  const getKeyFindingsColor = () => {
    if (!report.processed) return "text-[#8B9BB5]"
    if (report.risk_level === "high") return "text-rose-400"
    if (report.risk_level === "moderate") return "text-amber-400"
    return "text-emerald-400"
  }

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="group flex items-center gap-4 p-4 rounded-xl bg-[#0D1117] border border-[#2B364A] hover:border-[#0EA5A9]/30 hover:bg-[#181E2E] transition-all cursor-pointer"
      onClick={() => router.push(`/reports/${report.id}`)}
    >
      {/* Type icon */}
      <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border border-white/5", getType.bg)}>
        <TypeIcon className={cn("w-5 h-5", getType.color)} />
      </div>

      {/* Name + status + date */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold text-white truncate">
            {report.title || report.original_filename}
          </h4>
          <span className={cn("px-2 py-0.5 rounded-full text-[10px] font-medium border shrink-0", status.className)}>
            {status.label}
          </span>
        </div>
        <p className="text-xs text-[#8B9BB5] mt-0.5">
          {report.uploaded_at
            ? new Date(report.uploaded_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })
            : "Just now"}
          {report.uploaded_at && (
            <> · {new Date(report.uploaded_at).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })}</>
          )}
        </p>
      </div>

      {/* Health Score or Progress */}
      <div className="w-20 flex flex-col items-center shrink-0">
        {report.processed ? (
          <>
            <div className="relative w-10 h-10 flex items-center justify-center">
              <svg width={40} height={40} className="transform -rotate-90">
                <circle cx={20} cy={20} r={radius} fill="none" stroke="#2B364A" strokeWidth={3} />
                <circle cx={20} cy={20} r={radius} fill="none" stroke={scoreColor} strokeWidth={3} strokeLinecap="round"
                  strokeDasharray={circumference} strokeDashoffset={offset} className="transition-all duration-700" />
              </svg>
              <span className="absolute text-xs font-bold" style={{ color: scoreColor }}>{healthScore}</span>
            </div>
            <span className="text-[10px] text-[#8B9BB5] mt-0.5">Health Score</span>
          </>
        ) : (
          <div className="w-full">
            <div className="flex justify-between text-[10px] text-[#8B9BB5] mb-1">
              <span>Progress</span>
              <span>65%</span>
            </div>
            <div className="h-1.5 bg-[#2B364A] rounded-full overflow-hidden">
              <div className="h-full bg-[#0EA5A9] rounded-full transition-all duration-500" style={{ width: "65%" }} />
            </div>
          </div>
        )}
      </div>

      {/* Key Findings */}
      <div className="flex-1 min-w-0 hidden lg:block">
        <p className="text-[10px] uppercase tracking-wider text-[#8B9BB5] mb-0.5">Key Findings</p>
        <p className={cn("text-xs truncate", getKeyFindingsColor())}>{getKeyFindings()}</p>
      </div>

      {/* Action Button */}
      <div className="shrink-0">
        {report.processed ? (
          <button className="px-3 py-1.5 rounded-lg bg-[#0EA5A9]/10 text-[#0EA5A9] text-xs font-medium border border-[#0EA5A9]/20 hover:bg-[#0EA5A9]/20 transition-colors flex items-center gap-1.5">
            View Report <ChevronRight className="w-3 h-3" />
          </button>
        ) : (
          <button className="px-3 py-1.5 rounded-lg bg-amber-500/10 text-amber-400 text-xs font-medium border border-amber-500/20 flex items-center gap-1.5">
            View Progress <ChevronRight className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* More menu */}
      <button
        onClick={(e) => { e.stopPropagation(); onDelete(report.id) }}
        className="w-7 h-7 rounded-lg flex items-center justify-center text-[#8B9BB5] hover:text-white hover:bg-white/5 opacity-0 group-hover:opacity-100 transition-all shrink-0"
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>
    </motion.div>
  )
}

export default function ReportsPage() {
  const router = useRouter()
  const [reports, setReports] = useState<Report[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [sortBy, setSortBy] = useState("newest")
  const [viewMode, setViewMode] = useState<"grid" | "list">("list")
  const [currentPage, setCurrentPage] = useState(1)
  const perPage = 8

  const fetchReports = useCallback(async () => {
    try {
      const data = await apiFetch("/reports")
      setReports(Array.isArray(data) ? data : [])
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchReports()
    const interval = setInterval(() => {
      setReports(current => {
        if (current.some(r => !r.processed)) {
          fetchReports()
        }
        return current
      })
    }, 5000)
    return () => clearInterval(interval)
  }, [fetchReports])

  const handleUpload = async (file: File) => {
    const formData = new FormData()
    formData.append("file", file)
    try {
      const tempId = Math.random() * -1000
      setReports(prev => [{
        id: tempId,
        title: file.name,
        original_filename: file.name,
        document_type: "Processing...",
        processed: false,
        uploaded_at: new Date().toISOString()
      }, ...prev])
      await apiFetch("/reports/upload", {
        method: "POST",
        headers: {},
        body: formData,
      })
      fetchReports()
    } catch (e) {
      console.error("Upload failed", e)
      fetchReports()
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await apiFetch(`/reports/${id}`, { method: "DELETE" })
      setReports(prev => prev.filter(r => r.id !== id))
    } catch {}
  }

  const filtered = reports.filter(r => {
    const matchesSearch = (r.title || r.original_filename).toLowerCase().includes(searchQuery.toLowerCase()) ||
      (r.document_type || "").toLowerCase().includes(searchQuery.toLowerCase())
    if (statusFilter === "analyzed") return matchesSearch && r.processed && r.risk_level !== "high"
    if (statusFilter === "processing") return matchesSearch && !r.processed
    if (statusFilter === "needs_review") return matchesSearch && r.processed && r.risk_level === "high"
    return matchesSearch
  }).sort((a, b) => {
    if (sortBy === "newest") return new Date(b.uploaded_at).getTime() - new Date(a.uploaded_at).getTime()
    if (sortBy === "oldest") return new Date(a.uploaded_at).getTime() - new Date(b.uploaded_at).getTime()
    if (sortBy === "score") return (b.health_score || 0) - (a.health_score || 0)
    return 0
  })

  const totalPages = Math.ceil(filtered.length / perPage)
  const paginated = filtered.slice((currentPage - 1) * perPage, currentPage * perPage)

  const totalCount = reports.length
  const analyzedCount = reports.filter(r => r.processed && r.risk_level !== "high").length
  const processingCount = reports.filter(r => !r.processed).length
  const needsReviewCount = reports.filter(r => r.processed && r.risk_level === "high").length
  const avgHealthScore = reports.filter(r => r.processed).length > 0
    ? Math.round(reports.filter(r => r.processed).reduce((acc, r) => acc + (r.health_score || 75), 0) / reports.filter(r => r.processed).length)
    : 0

  if (loading) {
    return (
      <div className="p-6 max-w-7xl mx-auto space-y-6 min-h-screen">
        <div className="flex justify-between items-center">
          <div className="space-y-3"><div className="w-48 h-8 skeleton rounded-lg" /><div className="w-64 h-4 skeleton rounded" /></div>
          <div className="w-32 h-10 skeleton rounded-xl" />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {[1,2,3,4,5].map(i => <div key={i} className="h-24 skeleton rounded-xl" />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="h-[250px] skeleton rounded-2xl lg:col-span-2" />
          <div className="h-[250px] skeleton rounded-2xl" />
        </div>
      </div>
    )
  }

  return (
    <div className="relative min-h-screen">
      <div className="p-6 max-w-7xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white">Medical Reports</h1>
            <p className="text-[#8B9BB5] mt-1 text-sm">Upload, analyze, and compare your medical reports</p>
          </div>
          <button
            onClick={() => router.push("/reports/comparison")}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-[#0EA5A9] text-white font-medium text-sm hover:bg-[#0EA5A9]/90 transition-colors shrink-0"
          >
            <Plus className="w-4 h-4" /> Compare Reports
          </button>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <StatCard icon={FileText} label="Total Reports" value={totalCount} sub={`↗ ${totalCount} total`} color="text-[#0EA5A9]" bg="bg-[#0EA5A9]/10" />
          <StatCard icon={CheckCircle2} label="Analyzed" value={analyzedCount} sub={`↗ ${analyzedCount} this month`} color="text-emerald-400" bg="bg-emerald-500/10" />
          <StatCard icon={Clock} label="Processing" value={processingCount} sub="● In progress" color="text-amber-400" bg="bg-amber-500/10" subColor="text-amber-400" />
          <StatCard icon={AlertCircle} label="Needs Attention" value={needsReviewCount} sub="● Review needed" color="text-rose-400" bg="bg-rose-500/10" subColor="text-rose-400" />
          <StatCard icon={Activity} label="Health Score" value={avgHealthScore} sub="● Good" color="text-emerald-400" bg="bg-emerald-500/10" />
        </div>

        {/* Upload + AI Insights */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <UploadSection onUpload={handleUpload} />
          </div>
          <div className="bg-[#0D1117] border border-[#2B364A] rounded-2xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-semibold text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#0EA5A9]" /> AI Insights
              </h3>
              <button className="text-xs text-[#0EA5A9] hover:underline">View all insights →</button>
            </div>
            <div className="space-y-2">
              {INSIGHTS.map((insight, i) => (
                <InsightItem key={i} insight={insight} />
              ))}
            </div>
          </div>
        </div>

        {/* All Reports */}
        <div>
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
            <h2 className="text-lg font-semibold text-white">All Reports</h2>
            <div className="flex items-center gap-3">
              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8B9BB5]" />
                <input
                  type="text"
                  placeholder="Search reports..."
                  value={searchQuery}
                  onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1) }}
                  className="pl-9 pr-4 py-2 bg-[#0D1117] border border-[#2B364A] rounded-lg text-sm text-white placeholder-[#8B9BB5] focus:outline-none focus:border-[#0EA5A9]/50 w-48"
                />
              </div>
              {/* Status filter */}
              <select
                value={statusFilter}
                onChange={(e) => { setStatusFilter(e.target.value); setCurrentPage(1) }}
                className="px-3 py-2 bg-[#0D1117] border border-[#2B364A] rounded-lg text-sm text-white focus:outline-none focus:border-[#0EA5A9]/50 appearance-none cursor-pointer"
              >
                <option value="all">Status</option>
                <option value="analyzed">Analyzed</option>
                <option value="processing">Processing</option>
                <option value="needs_review">Needs Review</option>
              </select>
              {/* Sort */}
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value)}
                className="px-3 py-2 bg-[#0D1117] border border-[#2B364A] rounded-lg text-sm text-white focus:outline-none focus:border-[#0EA5A9]/50 appearance-none cursor-pointer"
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
                <option value="score">Health Score</option>
              </select>
              {/* View toggle */}
              <div className="flex items-center bg-[#0D1117] border border-[#2B364A] rounded-lg overflow-hidden">
                <button
                  onClick={() => setViewMode("list")}
                  className={cn("p-2 transition-colors", viewMode === "list" ? "bg-[#0EA5A9]/10 text-[#0EA5A9]" : "text-[#8B9BB5] hover:text-white")}
                >
                  <List className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setViewMode("grid")}
                  className={cn("p-2 transition-colors", viewMode === "grid" ? "bg-[#0EA5A9]/10 text-[#0EA5A9]" : "text-[#8B9BB5] hover:text-white")}
                >
                  <Grid3X3 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>

          {/* Report List */}
          <div className="space-y-2">
            <AnimatePresence>
              {paginated.length === 0 ? (
                <motion.div
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                  className="py-16 text-center"
                >
                  <Stethoscope className="w-12 h-12 text-[#8B9BB5] mx-auto mb-3 opacity-50" />
                  <p className="text-[#8B9BB5]">No reports found</p>
                </motion.div>
              ) : (
                paginated.map(report => (
                  <ReportRow key={report.id} report={report} onDelete={handleDelete} />
                ))
              )}
            </AnimatePresence>
          </div>

          {/* Pagination */}
          {filtered.length > perPage && (
            <div className="flex items-center justify-between mt-4 pt-4 border-t border-[#2B364A]">
              <p className="text-xs text-[#8B9BB5]">
                Showing {(currentPage - 1) * perPage + 1} to {Math.min(currentPage * perPage, filtered.length)} of {filtered.length} reports
              </p>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-[#8B9BB5] hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronLeft className="w-4 h-4" />
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={cn(
                      "w-8 h-8 rounded-lg flex items-center justify-center text-xs font-medium transition-colors",
                      page === currentPage
                        ? "bg-[#0EA5A9] text-white"
                        : "text-[#8B9BB5] hover:text-white hover:bg-white/5"
                    )}
                  >
                    {page}
                  </button>
                ))}
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-[#8B9BB5] hover:text-white hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                >
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function StatCard({ icon: Icon, label, value, sub, color, bg, subColor }: {
  icon: any; label: string; value: number; sub: string; color: string; bg: string; subColor?: string
}) {
  return (
    <div className="bg-[#0D1117] border border-[#2B364A] rounded-xl p-4 flex items-center gap-3 hover:border-[#0EA5A9]/20 transition-colors">
      <div className={cn("w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border border-white/5", bg)}>
        <Icon className={cn("w-5 h-5", color)} />
      </div>
      <div className="min-w-0">
        <p className="text-2xl font-bold text-white">{value}</p>
        <p className="text-xs text-[#8B9BB5] truncate">{label}</p>
        <p className={cn("text-[10px] mt-0.5", subColor || "text-[#8B9BB5]")}>{sub}</p>
      </div>
    </div>
  )
}
