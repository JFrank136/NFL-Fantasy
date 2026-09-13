/** Name tools: canonicalization, alias map, fuzzy match (Jaro-like) */

export function tidyName(n: string) {
  return n.replace(/[\s\u00A0]+/g,' ').trim()
}

export function canonicalKey(name: string, pos?: string, team?: string) {
  const n = tidyName(name).toLowerCase()
  const p = (pos||'').toUpperCase()
  const t = (team||'').toUpperCase()
  return [n,p,t].join('|')
}

export type AliasMap = Record<string, string> // from -> to canonical name

// Simple Jaro-Winkler-ish similarity (not exact but works well enough for near matches)
export function similar(a: string, b: string) {
  a = tidyName(a).toLowerCase(); b = tidyName(b).toLowerCase()
  if (a === b) return 1
  const da = a.replace(/[^a-z]/g,''); const db = b.replace(/[^a-z]/g,'')
  const L = Math.max(da.length, db.length) || 1
  let matches = 0
  let i = 0, j = 0
  while (i < da.length && j < db.length) {
    if (da[i] === db[j]) { matches++; i++; j++; }
    else if (da[i] < db[j]) i++; else j++;
  }
  const prefix = (()=>{
    let k=0; while (k < Math.min(4,a.length,b.length) && a[k]===b[k]) k++; return k
  })()
  return (matches / L) * 0.9 + (prefix/4)*0.1
}

export function fuzzyLookup(target: string, candidates: string[], threshold = 0.92) {
  let best = {name:'', score:0}
  for (const c of candidates) {
    const s = similar(target, c)
    if (s > best.score) best = {name:c, score:s}
  }
  return best.score >= threshold ? best.name : null
}
