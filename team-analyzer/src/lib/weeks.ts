export function detectWeekFromName(name: string): number | null {
  const m = name.toLowerCase().match(/week\s*([0-9]{1,2})/)
  if (!m) return null
  const n = parseInt(m[1],10)
  if (n >= 1 && n <= 18) return n
  return null
}

export function detectSourceFromName(name: string): 'boone' | 'draftsharks' | null {
  const lower = name.toLowerCase()
  if (lower.includes('boone')) return 'boone'
  if (lower.includes('draftsharks')) return 'draftsharks'
  return null
}
