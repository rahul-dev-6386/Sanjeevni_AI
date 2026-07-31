"use client"

import { useState, useEffect, useRef } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { Search, X, Loader2, Trash2, ChevronRight } from "lucide-react"
import { apiFetch, processAutocompleteSuggestions, type SuggestionItem } from "@/lib/utils"

interface DrugSearchProps {
  query: string
  onQueryChange: (val: string) => void
  onSearch: () => void
  loading?: boolean
  onClearRecent?: () => void
}

export default function DrugSearch({
  query, onQueryChange, onSearch,
  loading, onClearRecent,
}: DrugSearchProps) {
  const [focused, setFocused] = useState(false)
  const [suggestions, setSuggestions] = useState<SuggestionItem[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const blurTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const submittedRef = useRef(false)

  useEffect(() => {
    if (submittedRef.current) {
      submittedRef.current = false
      return
    }
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const q = query.trim()
    if (q.length < 2) {
      setSuggestions([])
      setShowSuggestions(false)
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const data = await apiFetch(`/drugs/autocomplete?q=${encodeURIComponent(q)}`)
        const raw: string[] = data.drugs || []
        setSuggestions(processAutocompleteSuggestions(raw, q))
        setShowSuggestions(raw.length > 0)
      } catch {
        setSuggestions([])
        setShowSuggestions(false)
      }
    }, 200)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [query])

  const clearSuggestions = () => {
    if (blurTimeoutRef.current) clearTimeout(blurTimeoutRef.current)
    setSuggestions([])
    setShowSuggestions(false)
  }

  const submitSearch = () => {
    submittedRef.current = true
    clearSuggestions()
    onSearch()
  }

  const selectSuggestion = (val: string) => {
    submittedRef.current = true
    onQueryChange(val)
    clearSuggestions()
    setTimeout(() => onSearch(), 0)
  }

  const handleRecentClick = (term: string) => {
    submittedRef.current = true
    onQueryChange(term)
    clearSuggestions()
    setTimeout(() => onSearch(), 0)
  }

  return (
    <div className="relative space-y-3">
      <motion.div
        className={`flex items-center gap-2 rounded-2xl border bg-gradient-to-r from-[#111827] to-[#0F1420] px-4 transition-all duration-300 ${
          focused
            ? "border-[#0EA5A9]/50 shadow-lg shadow-[#0EA5A9]/10 ring-1 ring-[#0EA5A9]/20"
            : "border-white/[0.08] hover:border-white/[0.12]"
        }`}
        style={{ height: 60 }}
      >
        <Search size={20} className="shrink-0 text-[#8B9BB5]" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => { blurTimeoutRef.current = setTimeout(clearSuggestions, 150) }}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              submitSearch()
            } else if (e.key === "Escape") {
              clearSuggestions()
              inputRef.current?.blur()
            }
          }}
          placeholder="Search by drug name, generic name, brand name, or therapeutic class..."
          className="h-full flex-1 bg-transparent text-sm text-[#EDF2F7] placeholder:text-[#8B9BB5]/50 outline-none"
        />
        {query && (
          <button
            onClick={() => onQueryChange("")}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-[#5A6B87] transition-colors hover:bg-white/[0.06] hover:text-[#EDF2F7]"
          >
            <X size={16} />
          </button>
        )}
        <div className="flex items-center gap-1.5">
          <motion.button
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            onClick={submitSearch}
            disabled={loading || !query.trim()}
            className="flex items-center gap-1.5 rounded-xl bg-gradient-to-r from-[#0EA5A9] to-teal-500 px-5 py-2.5 text-sm font-medium text-white shadow-lg shadow-[#0EA5A9]/15 transition-all hover:shadow-[#0EA5A9]/25 disabled:opacity-40"
          >
            {loading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Search size={14} />
            )}
            Search
          </motion.button>
        </div>
      </motion.div>

      <AnimatePresence>
        {showSuggestions && suggestions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="absolute left-0 right-0 top-full z-50 mt-1 overflow-hidden rounded-xl border border-white/[0.08] bg-[#1A1F2E] shadow-xl"
          >
            {suggestions.map((s) => (
              <button
                key={s.primary + s.subtitle}
                onMouseDown={() => selectSuggestion(s.primary)}
                className="group flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-white/[0.06]"
              >
                <Search size={14} className="shrink-0 text-[#5A6B87]" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-[#D1D9E8]">{s.primary}</p>
                  <p className="truncate text-xs text-[#5A6B87]">{s.subtitle}</p>
                </div>
                <ChevronRight size={14} className="shrink-0 text-[#5A6B87] transition-colors group-hover:text-[#0EA5A9]" />
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-[10px] font-medium text-[#8B9BB5]/40">Recent:</span>
        {["Metformin", "Atorvastatin", "Lisinopril", "Omeprazole", "Losartan"].map((term) => (
          <motion.button
            key={term}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.95 }}
            onClick={() => handleRecentClick(term)}
            className="rounded-full border border-white/[0.06] bg-white/[0.02] px-2.5 py-0.5 text-[11px] text-[#5A6B87] transition-all hover:border-[#0EA5A9]/25 hover:bg-[#0EA5A9]/[0.03] hover:text-[#8B9BB5]"
          >
            {term}
          </motion.button>
        ))}
        {onClearRecent && (
          <button
            onClick={onClearRecent}
            className="ml-auto flex items-center gap-1 text-[10px] text-[#5A6B87] transition-colors hover:text-[#8B9BB5]"
          >
            <Trash2 size={11} />
            Clear all
          </button>
        )}
      </div>
    </div>
  )
}
