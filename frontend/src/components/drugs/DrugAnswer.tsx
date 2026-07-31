"use client"

import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { motion } from "framer-motion"
import {
  BookOpen, Bot, ArrowLeft, Database, Sparkles,
  CheckCircle, Activity, AlertTriangle, Shield, HeartPulse,
  Timer, Brain, FileText,
} from "lucide-react"
import { formatDrugName } from "@/lib/utils"

interface DrugAnswerProps {
  markdown: string
  references: string[]
  drugName: string
  isAi?: boolean
  onBack?: () => void
}

const SECTION_ICONS: Record<string, typeof FileText> = {
  overview: FileText,
  "indications": CheckCircle,
  "mechanism of action": Brain,
  "dosage": Timer,
  "dosage & administration": Timer,
  "contraindications": Shield,
  "warnings": AlertTriangle,
  "warnings & precautions": Shield,
  "side effects": AlertTriangle,
  "common side effects": AlertTriangle,
  "drug interactions": AlertTriangle,
  "interactions": AlertTriangle,
  "pregnancy": HeartPulse,
  "pregnancy & breastfeeding": HeartPulse,
  "monitoring": Activity,
  "patient counseling": Sparkles,
  "clinical pearls": Sparkles,
  "off-label uses": CheckCircle,
  "storage": FileText,
  "storage & handling": FileText,
  "overdose": AlertTriangle,
  "overdose & toxicity": AlertTriangle,
  "references": BookOpen,
}

function fixMarkdownHeadings(text: string): string {
  if (!text) return ""
  return text.replace(/^(#{1,6})([^\s#])/gm, "$1 $2")
}

function getSectionIcon(heading: string) {
  const key = heading.toLowerCase().trim()
  const Icon = Object.entries(SECTION_ICONS).find(([k]) => key.startsWith(k))?.[1]
  return Icon || FileText
}

function extractText(node: React.ReactNode): string {
  if (typeof node === "string") return node
  if (Array.isArray(node)) return node.map(extractText).join("")
  if (node && typeof node === "object" && "props" in node) {
    return extractText((node as any).props.children)
  }
  return ""
}

export default function DrugAnswer({
  markdown,
  references,
  drugName,
  isAi,
  onBack,
}: DrugAnswerProps) {
  const safeMarkdown = markdown || ""
  const processedMarkdown = fixMarkdownHeadings(safeMarkdown)
  const displayName = formatDrugName(drugName)

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
    >
      {/* Back link */}
      {onBack && (
        <button
          onClick={onBack}
          className="mb-4 flex items-center gap-1.5 text-xs text-[#8B9BB5] transition-colors hover:text-[#EDF2F7]"
        >
          <ArrowLeft size={14} />
          Back to search
        </button>
      )}

      {/* Status banner */}
      <div className="mb-6 flex items-start gap-3 rounded-xl border border-white/[0.08] bg-white/[0.02] px-4 py-3">
        {isAi ? (
          <Sparkles size={16} className="mt-0.5 shrink-0 text-[#0EA5A9]" />
        ) : (
          <Database size={16} className="mt-0.5 shrink-0 text-emerald-400" />
        )}
        <p className="text-xs leading-relaxed text-[#8B9BB5]">
          {isAi ? (
            <>
              <span className="font-medium text-[#0EA5A9]">AI Generated</span>
              {" — "}This answer was generated from medical textbooks and verified drug databases.
            </>
          ) : (
            <>
              <span className="font-medium text-emerald-400">Verified Database</span>
              {" — "}This information is sourced from DailyMed, OpenFDA, and RxNorm.
            </>
          )}
        </p>
      </div>

      {/* Markdown content */}
      <div
        className="prose prose-invert max-w-none
        prose-headings:text-[#EDF2F7] prose-headings:font-bold
        prose-h1:text-2xl prose-h1:mt-0
        prose-h2:text-[20px] prose-h2:mt-10 prose-h2:mb-4 prose-h2:font-semibold
        prose-h3:text-[17px] prose-h3:mt-8 prose-h3:mb-3
        prose-p:text-[16px] prose-p:text-[#B0BECD] prose-p:leading-[1.7]
        prose-strong:text-[#EDF2F7]
        prose-ul:text-[#B0BECD] prose-ol:text-[#B0BECD]
        prose-li:text-sm
        prose-hr:border-white/[0.06] prose-hr:my-8
        prose-blockquote:border-[#0EA5A9] prose-blockquote:bg-[#0EA5A9]/5 prose-blockquote:py-1 prose-blockquote:px-5 prose-blockquote:rounded-r-lg prose-blockquote:italic prose-blockquote:text-[#B0BECD]
        prose-code:text-[#0EA5A9] prose-code:bg-[#0EA5A9]/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-sm
        prose-pre:bg-[#111827] prose-pre:border prose-pre:border-white/[0.08] prose-pre:rounded-xl
      "
      >
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="mb-2 mt-0 text-2xl font-bold text-[#EDF2F7]">
                {children}
              </h1>
            ),
            h2: ({ children }) => {
              const text = extractText(children)
              const Icon = getSectionIcon(text)
              return (
                <h2 className="mb-4 mt-10 flex items-center gap-2.5 text-[20px] font-semibold text-[#EDF2F7]">
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[#0EA5A9]/10">
                    <Icon size={14} className="text-[#0EA5A9]" />
                  </div>
                  {children}
                </h2>
              )
            },
            h3: ({ children }) => (
              <h3 className="mb-3 mt-8 text-[17px] font-semibold text-[#EDF2F7]">
                {children}
              </h3>
            ),
            ul: ({ children }) => (
              <ul className="my-3 space-y-2">{children}</ul>
            ),
            li: ({ children }) => (
              <li className="flex items-start gap-2.5 text-sm text-[#B0BECD]">
                <CheckCircle size={15} className="mt-0.5 shrink-0 text-emerald-400" />
                <span>{children}</span>
              </li>
            ),
            blockquote: ({ children }) => (
              <blockquote className="my-4 border-l-4 border-[#0EA5A9] bg-[#0EA5A9]/5 py-2 px-5 rounded-r-lg italic text-[#B0BECD]">
                {children}
              </blockquote>
            ),
            table: ({ children }) => (
              <div className="my-4 overflow-x-auto rounded-xl border border-white/[0.08]">
                <table className="w-full text-sm">{children}</table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="sticky top-0 bg-[#111827]">{children}</thead>
            ),
            tr: ({ children }) => (
              <tr className="border-b border-white/[0.06] even:bg-white/[0.02]">{children}</tr>
            ),
            th: ({ children }) => (
              <th className="px-4 py-3 text-left text-xs font-semibold text-[#8B9BB5] uppercase tracking-wider">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="px-4 py-3 text-sm text-[#B0BECD]">
                {children}
              </td>
            ),
            p: ({ children }) => (
              <p className="my-2 text-[16px] text-[#B0BECD] leading-[1.7]">
                {children}
              </p>
            ),
            strong: ({ children }) => (
              <strong className="text-[#EDF2F7] font-semibold">{children}</strong>
            ),
            hr: () => (
              <hr className="my-8 border-white/[0.06]" />
            ),
          }}
        >
          {processedMarkdown}
        </ReactMarkdown>
      </div>

      {/* References */}
      {references && references.length > 0 && (
        <div className="mt-8 rounded-xl border border-white/[0.08] bg-white/[0.02] p-5">
          <div className="mb-3 flex items-center gap-2">
            <BookOpen size={14} className="text-[#0EA5A9]" />
            <p className="text-xs font-semibold text-[#EDF2F7]">References</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {references.map((ref, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1.5 rounded-lg border border-[#0EA5A9]/20 bg-[#0EA5A9]/10 px-2.5 py-1 text-[11px] font-medium text-[#0EA5A9]"
              >
                {ref}
              </span>
            ))}
          </div>
        </div>
      )}

      <p className="mt-6 text-center text-[10px] text-[#5A6B87]">
        Generated by Sanjeevni AI &middot; Always consult a healthcare professional
      </p>
    </motion.div>
  )
}
