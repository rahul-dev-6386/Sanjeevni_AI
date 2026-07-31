"use client"

import { useState, useCallback, useEffect } from "react"
import { motion } from "framer-motion"
import {
  Pill, AlertTriangle, Loader2,
  AlertCircle, ChevronRight,
  Sparkles, Bot,
} from "lucide-react"
import { apiFetch, formatDrugName } from "@/lib/utils"

import DrugSearch from "@/components/drugs/DrugSearch"
import HeroCard from "@/components/drugs/HeroCard"
import CategoryGrid from "@/components/drugs/CategoryGrid"
import PopularDrugCard from "@/components/drugs/PopularDrugCard"
import SafetyBanner from "@/components/drugs/SafetyBanner"
import DrugAnswer from "@/components/drugs/DrugAnswer"
import DisclaimerBar from "@/components/drugs/DisclaimerBar"

/* ── Types ── */

interface DrugInfo {
  generic_name: string | null
  brand_name: string | null
  drug_class: string | null
  pharmacologic_class: string | null
  rxnorm_id: string | null
  brand_names: string[] | null
}

interface DrugAnswerResponse {
  markdown: string
  references: string[]
}

type SearchPhase =
  | "idle"
  | "local_loading"
  | "local_results"
  | "no_match"
  | "ai_loading"
  | "ai_result"
  | "ai_error"
  | "answer_view"

/* ── Constants ── */

const POPULAR_DRUGS = [
  { name: "Metformin", drugClass: "Biguanide" },
  { name: "Lisinopril", drugClass: "ACE Inhibitor" },
  { name: "Atorvastatin", drugClass: "Statin" },
  { name: "Omeprazole", drugClass: "Proton Pump Inhibitor" },
  { name: "Levothyroxine", drugClass: "Thyroid Hormone" },
  { name: "Amlodipine", drugClass: "Calcium Channel Blocker" },
  { name: "Albuterol", drugClass: "Beta-2 Agonist" },
  { name: "Losartan", drugClass: "ARB" },
]

/* ── Main Page ── */

export default function DrugsPage() {
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<DrugInfo[]>([])
  const [phase, setPhase] = useState<SearchPhase>("idle")

  const [answerLoading, setAnswerLoading] = useState(false)
  const [answer, setAnswer] = useState<DrugAnswerResponse | null>(null)
  const [answerIsAi, setAnswerIsAi] = useState(false)
  const [source, setSource] = useState<string | null>(null)
  const [recentSearches, setRecentSearches] = useState<string[]>([])
  const [selecting, setSelecting] = useState(false)
  const [aiError, setAiError] = useState<string | null>(null)
  const [lastSearchedTerm, setLastSearchedTerm] = useState("")

  const isShowingAnswer = phase === "answer_view"

  /* ── Persist ── */
  useEffect(() => {
    try {
      const r = localStorage.getItem("medico_recent_drugs")
      if (r) setRecentSearches(JSON.parse(r))
    } catch { /* */ }
  }, [])

  const persist = (k: string, v: any) => localStorage.setItem(k, JSON.stringify(v))

  const saveRecent = (name: string) => {
    const upd = [name, ...recentSearches.filter((s) => s !== name)].slice(0, 10)
    setRecentSearches(upd)
    persist("medico_recent_drugs", upd)
  }

  const clearRecent = () => {
    setRecentSearches([])
    persist("medico_recent_drugs", [])
  }

  /* ── Phase 1: Local Database Search ── */

  const handleSearch = useCallback(async (q?: string) => {
    const term = (q || query).trim()
    if (!term) return

    setPhase("local_loading")
    setQuery(term)
    setLastSearchedTerm(term)
    setAnswer(null)
    setSource(null)
    setResults([])
    setAiError(null)
    setAnswerIsAi(false)

    try {
      const data = await apiFetch(`/drugs/search?q=${encodeURIComponent(term)}`)
      const drugs: DrugInfo[] = data.drugs || []
      if (drugs.length > 0) {
        setResults(drugs)
        setSource(data.source || null)
        setPhase("local_results")
      } else {
        setPhase("no_match")
      }
      saveRecent(term)
    } catch {
      setResults([])
      setPhase("no_match")
    }
  }, [query])

  /* ── Answer from local selection ── */

  const fetchAnswer = async (drugName: string) => {
    setAnswerLoading(true)
    setAnswer(null)
    try {
      const data = await apiFetch(`/drugs/answer?q=${encodeURIComponent(drugName)}`)
      setAnswer(data)
      setAnswerIsAi(false)
      setPhase("answer_view")
    } catch {
      setAnswer(null)
    } finally {
      setAnswerLoading(false)
    }
  }

  const selectDrug = (drug: DrugInfo) => {
    const name = drug.generic_name || drug.brand_name || ""
    setSelecting(true)
    fetchAnswer(name).finally(() => setSelecting(false))
    window.scrollTo({ top: 0, behavior: "smooth" })
  }

  /* ── Phase 2: AI Search ── */

  const handleAiSearch = async () => {
    const term = query.trim()
    if (!term) return

    setPhase("ai_loading")
    setAnswer(null)
    setResults([])
    setAiError(null)
    setAnswerIsAi(true)
    setLastSearchedTerm(term)

    try {
      const data = await apiFetch(`/drugs/ai-search?q=${encodeURIComponent(term)}`)
      setAnswer(data)
      setPhase("ai_result")
    } catch (e: any) {
      setAiError(e.message || "AI search failed. Please try again.")
      setPhase("ai_error")
    }
  }

  const handleCategoryClick = (name: string) => {
    setQuery(name)
    handleSearch(name)
  }

  const handlePopularClick = (name: string) => {
    setQuery(name)
    handleSearch(name)
  }

  const handleBack = () => {
    setPhase("idle")
    setAnswer(null)
    setResults([])
    setAnswerIsAi(false)
    setAiError(null)
    setLastSearchedTerm("")
  }

  /* ── Render ── */
  return (
    <div className="flex min-h-screen flex-col bg-[#090B10]">
      {/* Mobile header */}
      <div className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#090B10]/90 px-4 py-3 backdrop-blur-xl lg:hidden">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-[#0EA5A9] to-teal-600">
                  <Pill className="h-4 w-4 text-white" />
                </div>
                <span className="text-sm font-bold text-[#EDF2F7]">Drug Assistant</span>
              </div>
            </div>
          </div>

      <main className="flex-1">
        <div className="mx-auto max-w-7xl px-6 py-6 sm:px-8 lg:py-8">
            {/* Global Search Bar */}
            <div className="relative mb-6">
              <div className="pointer-events-none absolute -top-8 left-1/4 right-1/4 h-px bg-gradient-to-r from-transparent via-[#0EA5A9]/10 to-transparent" />
              <DrugSearch
                query={query}
                onQueryChange={setQuery}
                onSearch={() => handleSearch()}
                loading={phase === "local_loading"}
                onClearRecent={clearRecent}
              />
            </div>

            <div className="min-w-0 flex-1">
                {/* Loading Skeletons */}
                {phase === "local_loading" && (
                  <div className="animate-pulse space-y-4">
                    <div className="skeleton h-12 rounded-2xl" />
                    <div className="skeleton h-4 w-1/2 rounded-lg" />
                    <div className="skeleton h-4 w-3/4 rounded-lg" />
                    <div className="skeleton h-48 rounded-2xl" />
                  </div>
                )}

                {answerLoading && (
                  <div className="animate-pulse space-y-4">
                    <div className="skeleton h-8 w-1/3 rounded-lg" />
                    <div className="skeleton h-4 w-2/3 rounded-lg" />
                    <div className="skeleton h-32 rounded-2xl" />
                    <div className="skeleton h-24 rounded-2xl" />
                    <div className="skeleton h-16 rounded-2xl" />
                  </div>
                )}

                {/* AI Loading */}
                {phase === "ai_loading" && (
                  <div className="flex flex-col items-center justify-center py-16 text-center">
                    <div className="relative mb-6">
                      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-500 shadow-xl shadow-teal-500/20">
                        <Bot className="h-8 w-8 text-white" />
                      </div>
                      <div className="absolute -bottom-1 -right-1 flex h-6 w-6 items-center justify-center rounded-full bg-[#090B10]">
                        <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
                      </div>
                    </div>
                    <p className="mb-2 text-lg font-semibold text-[#EDF2F7]">AI is analyzing your query</p>
                    <p className="text-sm text-[#8B9BB5]">
                      Searching medical knowledge for &quot;{query}&quot;
                    </p>
                    <Loader2 className="mt-4 h-5 w-5 animate-spin text-[#0EA5A9]" />
                  </div>
                )}

                {/* AI Error */}
                {phase === "ai_error" && (
                  <div className="flex flex-col items-center justify-center py-12 text-center">
                    <AlertCircle className="mx-auto mb-3 h-10 w-10 text-red-400/60" />
                    <p className="text-sm text-[#8B9BB5]">AI search failed</p>
                    {aiError && <p className="mt-1 text-xs text-[#8B9BB5]/60">{aiError}</p>}
                    <button
                      onClick={handleAiSearch}
                      className="mt-4 flex items-center gap-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 px-5 py-2.5 text-sm font-semibold text-white shadow-lg transition-all hover:shadow-teal-500/20"
                    >
                      <Bot className="h-4 w-4" />
                      Try again
                    </button>
                  </div>
                )}

                {/* Idle state */}
                {phase === "idle" && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8">
                    <HeroCard onSearch={handlePopularClick} />
                    <CategoryGrid onCategoryClick={handleCategoryClick} />
                    <section>
                      <div className="mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#0EA5A9]/10">
                            <Pill size={14} className="text-[#0EA5A9]" />
                          </div>
                          <h2 className="text-sm font-semibold text-[#EDF2F7]">Popular Drugs</h2>
                        </div>
                        <span className="rounded-full border border-white/[0.06] bg-white/[0.03] px-2.5 py-0.5 text-[11px] text-[#8B9BB5]">{POPULAR_DRUGS.length} medications</span>
                      </div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                        {POPULAR_DRUGS.map((drug, i) => (
                          <PopularDrugCard
                            key={drug.name}
                            name={drug.name}
                            drugClass={drug.drugClass}
                            index={i}
                            onClick={() => handlePopularClick(drug.name)}
                          />
                        ))}
                      </div>
                    </section>
                    <SafetyBanner />
                  </motion.div>
                )}

                {/* Local Results */}
                {phase === "local_results" && results.length > 0 && !selecting && (
                  <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-2">
                    <div className="mb-3 flex items-center justify-between">
                      <p className="text-xs text-[#8B9BB5]">
                        Found <span className="font-medium text-[#EDF2F7]">{results.length}</span> result{results.length > 1 ? "s" : ""} in local database
                        {source && source !== "local" && <span> (sources: {source})</span>}
                      </p>
                    </div>
                    {results.map((drug, i) => (
                      <motion.button
                        key={drug.generic_name || i}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.03 }}
                        onClick={() => selectDrug(drug)}
                        className="group flex w-full items-center gap-4 rounded-2xl border border-white/[0.08] bg-gradient-to-r from-white/[0.04] to-transparent p-4 text-left transition-all hover:border-[#0EA5A9]/30 hover:bg-[#0EA5A9]/[0.03] hover:shadow-lg hover:shadow-[#0EA5A9]/5"
                      >
                        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#0EA5A9] to-teal-600 shadow-lg shadow-[#0EA5A9]/15">
                          <Pill className="h-5 w-5 text-white" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-[#EDF2F7] transition-colors group-hover:text-[#0EA5A9]">{formatDrugName(drug.brand_name || drug.generic_name || "")}</p>
                          <p className="truncate text-xs text-[#8B9BB5]">
                            {drug.generic_name && drug.brand_name ? `Generic: ${formatDrugName(drug.generic_name)}` : formatDrugName(drug.drug_class || "") || "Medication"}
                          </p>
                        </div>
                        <ChevronRight className="h-4 w-4 shrink-0 text-[#8B9BB5] transition-colors group-hover:text-[#0EA5A9]" />
                      </motion.button>
                    ))}
                    <div className="pt-2 text-center">
                      <button
                        onClick={handleAiSearch}
                        className="inline-flex items-center gap-2 text-xs text-[#8B9BB5] transition-colors hover:text-emerald-300"
                      >
                        <Sparkles className="h-3 w-3" />
                        {lastSearchedTerm && <>Ask AI about &quot;{lastSearchedTerm}&quot;</>}
                      </button>
                    </div>
                  </motion.div>
                )}

                {/* No Match */}
                {phase === "no_match" && !selecting && (
                  <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="flex flex-col items-center justify-center py-16 text-center"
                  >
                    <div className="mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-amber-500/15 bg-amber-500/10">
                      <AlertTriangle className="h-7 w-7 text-amber-400/70" />
                    </div>
                    <h3 className="mb-2 text-lg font-semibold text-[#EDF2F7]">No relevant medicine found</h3>
                    <p className="mb-2 max-w-md text-sm text-[#8B9BB5]">
                      &quot;{lastSearchedTerm || query}&quot; was not found in the local verified database.
                    </p>
                    <p className="mb-6 max-w-sm text-xs text-[#8B9BB5]/60">
                      This will bypass the local database and use the AI model to answer your query.
                    </p>
                    <button
                      onClick={handleAiSearch}
                      className="group flex items-center gap-3 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-500 px-6 py-3.5 text-sm font-semibold text-white shadow-xl shadow-teal-500/15 transition-all hover:-translate-y-0.5 hover:shadow-teal-500/25 active:scale-[0.98] active:translate-y-0"
                    >
                      <Bot className="h-5 w-5" />
                      Search with AI
                      <Sparkles className="h-4 w-4 text-emerald-200" />
                    </button>
                  </motion.div>
                )}

                {/* Drug Answer */}
                {(isShowingAnswer || phase === "ai_result") && answer && (
                  <DrugAnswer
                    markdown={answer.markdown}
                    references={answer.references}
                    drugName={lastSearchedTerm || query}
                    isAi={answerIsAi || phase === "ai_result"}
                    onBack={handleBack}
                  />
                )}
              </div>
          </div>
        </main>

        <DisclaimerBar />
      </div>
  )
}
