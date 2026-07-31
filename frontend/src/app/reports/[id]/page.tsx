"use client"

import { useEffect, useState, useRef } from "react"
import { useRouter, useParams } from "next/navigation"
import { apiFetch } from "@/lib/utils"
import { motion, AnimatePresence } from "framer-motion"
import {
  ArrowLeft, FileText, Brain, Loader2, AlertTriangle,
  FlaskConical, Shield, TrendingUp, BarChart3, Activity,
  Calendar, User, Pill, ScanLine, Scan, Building2,
  ChevronDown, ChevronUp, ExternalLink, Download,
} from "lucide-react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import type { AIInsightItem, ComparisonItem, TimelineEventItem } from "@/components/features/reports/types"

const DOC_TYPE_META: Record<string, { icon: any; theme: string }> = {
  "Blood Test Report": { icon: FlaskConical, theme: "text-[#0EA5A9] bg-[#0EA5A9]/10 border-[#0EA5A9]/20" },
  "Prescription": { icon: Pill, theme: "text-violet-400 bg-violet-500/10 border-violet-500/20" },
  "X-Ray": { icon: ScanLine, theme: "text-blue-400 bg-blue-500/10 border-blue-500/20" },
  "MRI": { icon: Scan, theme: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20" },
  "CT Scan": { icon: Scan, theme: "text-sky-400 bg-sky-500/10 border-sky-500/20" },
  "ECG": { icon: Activity, theme: "text-red-400 bg-red-500/10 border-red-500/20" },
  "Discharge Summary": { icon: Building2, theme: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
  "Vaccination Record": { icon: FileText, theme: "text-[#0EA5A9] bg-[#0EA5A9]/10 border-[#0EA5A9]/20" },
  "Medical Certificate": { icon: FileText, theme: "text-[#8B9BB5] bg-[#212A3C] border-[#2B364A]" },
  "Insurance Document": { icon: FileText, theme: "text-blue-400 bg-blue-500/10 border-blue-500/20" },
  "General Medical Report": { icon: FileText, theme: "text-[#0EA5A9] bg-[#0EA5A9]/10 border-[#0EA5A9]/20" },
}

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
}

function TabButton({ active, icon: Icon, label, onClick }: { active: boolean; icon: any; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all duration-200 ${
        active
          ? "bg-[#0EA5A9]/10 text-[#0EA5A9] border border-[#0EA5A9]/20"
          : "text-[#8B9BB5] border border-transparent hover:text-[#EDF2F7] hover:bg-[#181E2E]"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  )
}

function LabCard({ lab }: { lab: any }) {
  const isAbnormal = lab.is_abnormal || lab.flag === "HIGH" || lab.flag === "LOW"
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`clinical-card-hover relative overflow-hidden ${isAbnormal ? 'border-l-4 border-l-red-500' : 'border-l-4 border-l-[#0EA5A9]'}`}
    >
      <div className="absolute top-0 right-0 p-3 opacity-10">
        <FlaskConical className="w-12 h-12" />
      </div>
      <p className="clinical-label truncate pr-8">{lab.test_name || lab.marker}</p>
      <div className="mt-2 flex items-baseline gap-1">
        <span className={`text-2xl font-bold tracking-tight ${isAbnormal ? 'text-red-400' : 'text-[#EDF2F7]'}`}>
          {lab.value_text || lab.value}
        </span>
        <span className="text-xs text-[#8B9BB5] font-mono">{lab.unit}</span>
      </div>
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-[#2B364A]">
        <div className="flex flex-col">
          <span className="text-[9px] text-[#8B9BB5] uppercase tracking-widest">Reference Range</span>
          <span className="text-xs font-mono text-[#D1D9E8] mt-0.5">{lab.reference_range || lab.range || "N/A"}</span>
        </div>
        {lab.flag && (
          <span className={
            lab.flag === "NORMAL" ? "medical-badge-teal" : 
            lab.flag === "HIGH" ? "medical-badge-red" : 
            lab.flag === "LOW" ? "medical-badge-amber" : 
            "medical-badge"
          }>
            {lab.flag}
          </span>
        )}
      </div>
    </motion.div>
  )
}

export default function ReportDetailPage() {
  const router = useRouter()
  const params = useParams()
  const reportId = Number(params.id)
  const [loading, setLoading] = useState(true)
  const [summary, setSummary] = useState<any>(null)
  const [structured, setStructured] = useState<any>(null)
  const [labValues, setLabValues] = useState<any[]>([])
  const [findings, setFindings] = useState<any[]>([])
  const [riskScores, setRiskScores] = useState<any>(null)
  const [insights, setInsights] = useState<AIInsightItem[]>([])
  const [timeline, setTimeline] = useState<TimelineEventItem[]>([])
  const [biomarkers, setBiomarkers] = useState<any[]>([])
  const [comparisons, setComparisons] = useState<ComparisonItem[]>([])
  const [activeTab, setActiveTab] = useState("overview")
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set())
  const [exporting, setExporting] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)
  const printableRef = useRef<HTMLDivElement>(null)

  useEffect(() => { loadAll() }, [])

  const handleExportPdf = async () => {
    if (!printableRef.current) return
    setExporting(true)
    try {
      const html2canvas = (await import("html2canvas")).default
      const { default: jsPDF } = await import("jspdf")
      
      const element = printableRef.current
      element.style.display = "block"
      
      const canvas = await html2canvas(element, {
        backgroundColor: "#0B0F1A",
        scale: 2,
        useCORS: true,
      })
      
      element.style.display = "none"
      
      const imgData = canvas.toDataURL("image/png")
      const pdf = new jsPDF("p", "mm", "a4")
      const pageWidth = pdf.internal.pageSize.getWidth()
      const imgWidth = pageWidth - 20
      const imgHeight = (canvas.height * imgWidth) / canvas.width
      let heightLeft = imgHeight
      let position = 10

      pdf.addImage(imgData, "PNG", 10, position, imgWidth, imgHeight)
      heightLeft -= pdf.internal.pageSize.getHeight() - 20

      while (heightLeft > 0) {
        position = heightLeft - imgHeight + 10
        pdf.addPage()
        pdf.addImage(imgData, "PNG", 10, position, imgWidth, imgHeight)
        heightLeft -= pdf.internal.pageSize.getHeight() - 20
      }

      pdf.save(`${summary?.title || "report"}-${new Date().toISOString().split("T")[0]}.pdf`)
    } catch {
      console.error("PDF export failed")
    } finally {
      setExporting(false)
    }
  }

  const toggleSection = (id: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const loadAll = async () => {
    setLoading(true)
    try {
      const [summaryData, labData, findingsData, riskData, insightData, timelineData, bioData, compData] = await Promise.allSettled([
        apiFetch(`/intelligence/reports/${reportId}/summary`),
        apiFetch(`/intelligence/reports/${reportId}/lab-values`),
        apiFetch(`/intelligence/reports/${reportId}/findings`),
        apiFetch(`/intelligence/reports/${reportId}/risk-scores`),
        apiFetch(`/intelligence/reports/${reportId}/insights`),
        apiFetch(`/intelligence/reports/${reportId}/timeline`),
        apiFetch(`/intelligence/reports/${reportId}/biomarkers`),
        apiFetch(`/intelligence/reports/${reportId}/comparison`),
      ])

      if (summaryData.status === "fulfilled") {
        setSummary(summaryData.value)
        setStructured(summaryData.value.structured_data || {})
      }
      if (labData.status === "fulfilled") setLabValues(labData.value.lab_values || [])
      if (findingsData.status === "fulfilled") setFindings(findingsData.value.findings || [])
      if (riskData.status === "fulfilled") setRiskScores(riskData.value)
      if (insightData.status === "fulfilled") setInsights(insightData.value.insights || [])
      if (timelineData.status === "fulfilled") setTimeline(timelineData.value.timeline || [])
      if (bioData.status === "fulfilled") setBiomarkers(bioData.value.biomarkers || [])
      if (compData.status === "fulfilled") setComparisons(compData.value.comparisons || [])
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[calc(100vh-4rem)] bg-noise">
        <div className="flex flex-col items-center gap-6">
          <div className="relative">
            <div className="absolute inset-0 bg-[#0EA5A9] rounded-full blur-2xl opacity-20 animate-pulse-glow" />
            <div className="w-16 h-16 rounded-2xl bg-[#181E2E] border border-[#2B364A] flex items-center justify-center relative z-10 shadow-2xl">
              <Loader2 className="h-8 w-8 text-[#0EA5A9] animate-spin" />
            </div>
          </div>
          <div className="text-center">
            <p className="text-sm font-medium text-[#EDF2F7]">Synthesizing Analysis</p>
            <p className="text-xs text-[#8B9BB5] mt-1">Cross-referencing medical databases...</p>
          </div>
        </div>
      </div>
    )
  }

  if (!summary) {
    return (
      <div className="p-6 max-w-7xl mx-auto flex items-center justify-center min-h-[60vh]">
        <div className="clinical-empty w-full max-w-md">
          <div className="clinical-empty-icon">
            <AlertTriangle className="h-6 w-6 text-amber-500" />
          </div>
          <h3 className="clinical-empty-title">Dossier Unavailable</h3>
          <p className="clinical-empty-text">This medical report could not be found or has been removed from the system.</p>
          <button onClick={() => router.push("/reports")} className="btn-clinical">
            <ArrowLeft className="h-4 w-4" />
            Return to Directory
          </button>
        </div>
      </div>
    )
  }

  const docType = summary.document_type || "General Medical Report"
  const meta = DOC_TYPE_META[docType] || { icon: FileText, theme: "text-[#0EA5A9] bg-[#0EA5A9]/10 border-[#0EA5A9]/20" }
  const TypeIcon = meta.icon
  const isBlood = docType === "Blood Test Report"

  const tabs = [
    { id: "overview", label: "Clinical Overview", icon: Brain },
    ...(isBlood || labValues.length > 0 ? [{ id: "labs", label: "Laboratory Results", icon: FlaskConical }] : []),
    { id: "findings", label: "Identified Findings", icon: AlertTriangle },
    ...(riskScores ? [{ id: "risks", label: "Risk Assessment", icon: Shield }] : []),
    ...(insights.length > 0 ? [{ id: "insights", label: "AI Insights", icon: TrendingUp }] : []),
    ...(biomarkers.length > 0 ? [{ id: "biomarkers", label: "Tracked Biomarkers", icon: Activity }] : []),
    ...(comparisons.length > 0 ? [{ id: "comparison", label: "Historical Comparison", icon: BarChart3 }] : []),
    ...(timeline.length > 0 ? [{ id: "timeline", label: "Patient Timeline", icon: Calendar }] : []),
  ]

  const renderTab = (tabId: string = activeTab) => {
    switch (tabId) {
      case "overview":
        return (
          <div className="space-y-6">
            
            {/* Primary Metrics Row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Health Score */}
              {summary.health_score != null && (
                <div className="clinical-card flex flex-col justify-between">
                  <div className="flex items-center justify-between mb-4">
                    <span className="clinical-label">Health Score Index</span>
                    <Activity className="h-4 w-4 text-[#8B9BB5]" />
                  </div>
                  <div className="flex items-end gap-4">
                    <div className="text-5xl font-bold tracking-tight text-[#EDF2F7]">
                      {summary.health_score}
                    </div>
                    <div className="pb-1 text-sm text-[#8B9BB5]">
                      / 100
                    </div>
                  </div>
                  <div className="mt-4 pt-4 border-t border-[#2B364A]">
                    <p className="text-xs text-[#8B9BB5]">
                      {summary.health_score >= 80 ? "Optimal health indicators." :
                       summary.health_score >= 60 ? "Satisfactory — monitor closely." :
                       "Attention required — consult physician."}
                    </p>
                  </div>
                </div>
              )}

              {/* Patient Info */}
              {(structured.patient_info || structured.patient_name) && (
                <div className="clinical-card md:col-span-2">
                  <div className="flex items-center gap-2 mb-4">
                    <User className="h-4 w-4 text-[#8B9BB5]" />
                    <span className="clinical-label">Patient Demographics</span>
                  </div>
                  
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-y-4 gap-x-6">
                    <div className="flex flex-col">
                      <span className="data-label">Full Name</span>
                      <span className="data-value mt-1">{structured.patient_info?.name || structured.patient_name || "Unknown"}</span>
                    </div>
                    {(structured.patient_info?.age || structured.age) && (
                      <div className="flex flex-col">
                        <span className="data-label">Age</span>
                        <span className="data-value mt-1">{structured.patient_info?.age || structured.age}</span>
                      </div>
                    )}
                    {(structured.patient_info?.gender || structured.gender) && (
                      <div className="flex flex-col">
                        <span className="data-label">Sex</span>
                        <span className="data-value mt-1">{structured.patient_info?.gender || structured.gender}</span>
                      </div>
                    )}
                    {structured.hospital && (
                      <div className="flex flex-col">
                        <span className="data-label">Facility</span>
                        <span className="data-value mt-1">{structured.hospital}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* AI Synthesized Report */}
            {summary.ai_summary && (
              <div className="clinical-card relative overflow-hidden">
                <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none">
                  <Brain className="w-32 h-32" />
                </div>
                <div className="flex items-center gap-2 mb-6 border-b border-[#2B364A] pb-4">
                  <div className="p-1.5 rounded bg-[#0EA5A9]/10">
                    <Brain className="h-4 w-4 text-[#0EA5A9]" />
                  </div>
                  <h2 className="text-sm font-semibold text-[#EDF2F7] tracking-wide uppercase">AI Synthesized Analysis</h2>
                </div>
                <div className="clinical-prose max-w-none">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {summary.ai_summary}
                  </ReactMarkdown>
                </div>
              </div>
            )}

            {/* Vitals Grid */}
            {structured.vitals && Object.keys(structured.vitals).length > 0 && (
              <div className="clinical-card">
                 <div className="flex items-center gap-2 mb-4">
                   <Activity className="h-4 w-4 text-[#0EA5A9]" /> 
                   <span className="clinical-label">Recorded Vitals</span>
                 </div>
                 <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    {Object.entries(structured.vitals).map(([k, v]: any) => (
                       <div key={k} className="p-3 bg-[#212A3C] rounded-lg border border-[#2B364A]">
                          <p className="data-label capitalize">{k.replace("_", " ")}</p>
                          <p className="data-value mt-1.5 text-lg">{v}</p>
                       </div>
                    ))}
                 </div>
              </div>
            )}
            
            {/* Medications List */}
            {structured.medications && structured.medications.length > 0 && (
              <div className="clinical-card">
                 <div className="flex items-center gap-2 mb-4">
                   <Pill className="h-4 w-4 text-[#0EA5A9]" /> 
                   <span className="clinical-label">Prescribed Medications</span>
                 </div>
                 <div className="divide-y divide-[#2B364A]">
                   {structured.medications.map((m: any, i: number) => (
                     <div key={i} className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-2 first:pt-0 last:pb-0">
                       <div className="flex items-center gap-3">
                         <span className="text-[#EDF2F7] font-medium">{m.name}</span>
                         {m.strength && <span className="medical-badge-blue">{m.strength}</span>}
                       </div>
                       {m.frequency && <span className="text-sm text-[#8B9BB5]">{m.frequency}</span>}
                     </div>
                   ))}
                 </div>
              </div>
            )}

            {/* Extra Extracted Sections */}
            {structured.sections && structured.sections.length > 0 && (
              <div className="space-y-3">
                <h3 className="clinical-label ml-1">Additional Document Sections</h3>
                {structured.sections.map((section: any, i: number) => (
                  <div key={i} className="clinical-card p-0 overflow-hidden">
                    <button
                      onClick={() => toggleSection(`section-${i}`)}
                      className="w-full flex items-center justify-between p-4 bg-[#181E2E] hover:bg-[#1C2336] transition-colors"
                    >
                      <span className="text-sm font-semibold text-[#EDF2F7]">{section.title || section.section}</span>
                      {expandedSections.has(`section-${i}`) ? (
                        <ChevronUp className="h-4 w-4 text-[#8B9BB5]" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-[#8B9BB5]" />
                      )}
                    </button>
                    <AnimatePresence>
                      {expandedSections.has(`section-${i}`) && (
                        <motion.div 
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div className="p-4 pt-0 border-t border-[#2B364A]">
                            <p className="text-sm text-[#D1D9E8] leading-relaxed whitespace-pre-wrap mt-4">{section.content}</p>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))}
              </div>
            )}
          </div>
        )

      case "labs":
        return (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {labValues.length === 0 ? (
              <div className="col-span-full clinical-empty">
                <FlaskConical className="h-8 w-8 text-[#8B9BB5] mb-4 opacity-50" />
                <p className="clinical-empty-text">No laboratory values extracted from this report.</p>
              </div>
            ) : (
              labValues.map((lab, i) => <LabCard key={i} lab={lab} />)
            )}
          </div>
        )

      case "findings":
        return (
          <div className="space-y-4">
            {findings.length === 0 && (
              <div className="clinical-empty">
                <AlertTriangle className="h-8 w-8 text-[#8B9BB5] mb-4 opacity-50" />
                <p className="clinical-empty-text">No distinct findings mapped.</p>
              </div>
            )}
            {findings.map((section, i) => (
              <div key={i} className="clinical-card">
                <h3 className="text-sm font-semibold text-[#EDF2F7] mb-4 border-b border-[#2B364A] pb-3">{section.section}</h3>
                {section.items?.length > 0 ? (
                  <ul className="space-y-3">
                    {section.items.map((item: string, j: number) => (
                      <li key={j} className="text-sm text-[#D1D9E8] flex items-start gap-3">
                        <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#0EA5A9] shrink-0" />
                        <span className="leading-relaxed">{item}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-[#8B9BB5] italic">No items listed.</p>
                )}
              </div>
            ))}
          </div>
        )

      case "risks":
        return (
          <div className="space-y-4">
            {riskScores?.ml_predictions?.map((p: any, i: number) => (
              <div key={i} className="clinical-card border-l-4" style={{
                borderLeftColor: p.risk_level === "high" ? "#EF4444" : p.risk_level === "moderate" ? "#F59E0B" : "#22C55E"
              }}>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-3">
                  <div>
                    <h4 className="text-base font-semibold text-[#EDF2F7]">{p.condition}</h4>
                    <p className="clinical-label mt-1">Source: {p.source}</p>
                  </div>
                  <span className={
                    p.risk_level === "high" ? "medical-badge-red" : 
                    p.risk_level === "moderate" ? "medical-badge-amber" : 
                    "medical-badge-teal"
                  }>
                    {p.risk_level.toUpperCase()} {p.risk_score ? `— ${p.risk_score}%` : ""}
                  </span>
                </div>
                {p.message && <p className="text-sm text-[#D1D9E8] leading-relaxed">{p.message}</p>}
                {p.source_url && (
                  <a href={p.source_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-xs font-medium text-[#0EA5A9] hover:text-[#0D9498] mt-4 transition-colors">
                    <ExternalLink className="h-3.5 w-3.5" />
                    Review Clinical Source
                  </a>
                )}
              </div>
            ))}
          </div>
        )

      case "insights":
        return (
          <div className="space-y-4">
            {insights.map((insight, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.05 }}
                className="clinical-card flex gap-4"
              >
                <div className="shrink-0 mt-1">
                  <div className={`p-2 rounded-lg ${
                    insight.severity === "critical" ? "bg-red-500/10 text-red-400" :
                    insight.severity === "warning" || insight.severity === "attention" ? "bg-amber-500/10 text-amber-400" :
                    "bg-[#0EA5A9]/10 text-[#0EA5A9]"
                  }`}>
                    <TrendingUp className="h-5 w-5" />
                  </div>
                </div>
                <div className="flex-1">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                    <h4 className="text-sm font-semibold text-[#EDF2F7]">{insight.title}</h4>
                    <span className={
                      insight.severity === "critical" ? "medical-badge-red" :
                      insight.severity === "warning" || insight.severity === "attention" ? "medical-badge-amber" :
                      "medical-badge-teal"
                    }>{insight.severity.toUpperCase()}</span>
                  </div>
                  {insight.description && <p className="text-sm text-[#D1D9E8] leading-relaxed">{insight.description}</p>}
                </div>
              </motion.div>
            ))}
          </div>
        )

      case "biomarkers":
        return (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {biomarkers.map((b, i) => (
              <div key={i} className="clinical-card">
                <p className="clinical-label mb-2">{b.name}</p>
                <div className="flex items-baseline gap-1.5">
                  <span className={`text-2xl font-bold ${b.is_abnormal ? "text-red-400" : "text-[#EDF2F7]"}`}>
                    {b.value_text || b.value}
                  </span>
                  <span className="text-xs text-[#8B9BB5] font-mono">{b.unit}</span>
                </div>
                {b.reference_range && (
                  <div className="mt-3 pt-3 border-t border-[#2B364A] flex justify-between items-center">
                    <span className="text-[10px] text-[#8B9BB5] uppercase tracking-wider">Range</span>
                    <span className="text-xs text-[#D1D9E8] font-mono">{b.reference_range}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
        )

      case "comparison":
        return (
          <div className="space-y-4">
            {comparisons.map((comp, i) => (
              <div key={i} className="clinical-card">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-[#EDF2F7] mb-3">{comp.biomarker}</h4>
                    <div className="flex items-center gap-4 bg-[#212A3C] p-3 rounded-lg border border-[#2B364A] w-fit">
                      <div className="flex flex-col">
                        <span className="text-[10px] text-[#8B9BB5] uppercase mb-1">Previous</span>
                        <span className="font-mono text-sm text-[#8B9BB5]">{comp.previous} {comp.unit}</span>
                      </div>
                      <div className="text-[#8B9BB5]/30 px-2">→</div>
                      <div className="flex flex-col">
                        <span className="text-[10px] text-[#8B9BB5] uppercase mb-1">Current</span>
                        <span className="font-mono text-sm text-[#EDF2F7] font-medium">{comp.current} {comp.unit}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2">
                    <span className={
                      comp.status === "improved" ? "medical-badge-teal" :
                      comp.status === "worsened" ? "medical-badge-red" :
                      "medical-badge"
                    }>{comp.status.toUpperCase()}</span>
                    
                    {comp.change !== "N/A" && comp.change !== "0" && (
                      <span className={`text-xs font-bold font-mono ${comp.status === "worsened" ? "text-red-400" : "text-[#0EA5A9]"}`}>
                        Δ {comp.change} {comp.unit}
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )

      case "timeline":
        return (
          <div className="relative pl-4 sm:pl-8 py-4">
            <div className="absolute left-[27px] sm:left-[43px] top-0 bottom-0 w-px bg-[#2B364A]" />
            <div className="space-y-8">
              {timeline.map((event, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: i * 0.08 }}
                  className="relative pl-8"
                >
                  <div className={`absolute left-[-5px] top-1.5 w-3 h-3 rounded-full border-2 bg-[#0B0F1A] ${
                    event.severity === "critical" ? "border-red-500" :
                    event.severity === "warning" ? "border-amber-500" :
                    "border-[#0EA5A9]"
                  }`} />
                  <div className="clinical-card">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-2">
                      <h4 className="text-sm font-semibold text-[#EDF2F7]">{event.title}</h4>
                      {event.date && (
                        <span className="text-xs font-mono text-[#8B9BB5] bg-[#212A3C] px-2 py-1 rounded">
                          {new Date(event.date).toLocaleDateString("en-US", {
                            month: "short", day: "numeric", year: "numeric"
                          })}
                        </span>
                      )}
                    </div>
                    {event.description && (
                      <p className="text-sm text-[#D1D9E8] leading-relaxed">{event.description}</p>
                    )}
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        )

      default:
        return null
    }
  }

  return (
    <div className="bg-noise min-h-screen">
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="p-4 lg:p-8 max-w-6xl mx-auto space-y-8"
      >
        {/* Dossier Header */}
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4"
        >
          <div className="flex items-center gap-4">
            <button onClick={() => router.push("/reports")} className="btn-clinical-icon border border-[#2B364A] bg-[#181E2E] shadow-sm">
              <ArrowLeft className="h-5 w-5" />
            </button>
            <div>
              <div className="flex items-center gap-3">
                <div className={`px-2.5 py-1 rounded-md border text-xs font-medium uppercase tracking-wider ${meta.theme}`}>
                  {docType}
                </div>
                <span className="text-xs text-[#8B9BB5] font-mono">
                  REF-{summary.id?.toString().padStart(6, '0')}
                </span>
              </div>
              <h1 className="text-2xl font-bold text-[#EDF2F7] mt-2 tracking-tight">{summary.title}</h1>
            </div>
          </div>
          <div className="flex items-center gap-3 self-start sm:self-auto">
            <button
              onClick={handleExportPdf}
              disabled={exporting}
              className="btn-clinical-secondary"
            >
              {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
              {exporting ? "Generating..." : "Export PDF"}
            </button>
          </div>
        </motion.div>

        {/* Tab Navigation */}
        <div className="flex gap-2 overflow-x-auto pb-1 border-b border-[#2B364A] scrollbar-hide">
          {tabs.map((tab) => (
            <TabButton
              key={tab.id}
              active={activeTab === tab.id}
              icon={tab.icon}
              label={tab.label}
              onClick={() => setActiveTab(tab.id)}
            />
          ))}
        </div>

        {/* Dynamic Content */}
        <motion.div
          key={activeTab}
          ref={contentRef}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
        >
          {renderTab()}
        </motion.div>

        {/* Hidden PDF Export Container */}
        <div 
          ref={printableRef} 
          style={{ 
            display: "none",
            position: "absolute", 
            left: "-9999px", 
            top: "-9999px", 
            width: "1000px", 
            padding: "60px", 
            backgroundColor: "#0B0F1A", 
            color: "#EDF2F7",
            fontFamily: "Inter, sans-serif"
          }}
        >
          <div className="border-b border-[#2B364A] pb-8 mb-8 flex items-start gap-6">
             <div className="p-4 rounded-xl bg-[#212A3C] border border-[#2B364A]">
               <TypeIcon className="h-10 w-10 text-[#0EA5A9]" />
             </div>
             <div>
               <p className="text-[#0EA5A9] text-sm font-bold tracking-widest uppercase mb-2">{docType}</p>
               <h1 className="text-4xl font-bold tracking-tight mb-2">{summary.title}</h1>
               <p className="text-[#8B9BB5] font-mono">
                 Document ID: REF-{summary.id?.toString().padStart(6, '0')} • 
                 Generated: {new Date().toLocaleDateString()}
               </p>
             </div>
          </div>
          
          <div className="space-y-16">
            {tabs.map(tab => (
              <div key={tab.id} className="space-y-6">
                <div className="flex items-center gap-3 border-b border-[#2B364A] pb-4">
                  <tab.icon className="h-6 w-6 text-[#0EA5A9]" />
                  <h2 className="text-2xl font-bold">{tab.label}</h2>
                </div>
                <div>
                  {renderTab(tab.id)}
                </div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>
    </div>
  )
}
