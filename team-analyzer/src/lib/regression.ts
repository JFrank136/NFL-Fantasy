/**
 * Robust linear fit y = a + b*x using two-pass OLS + MAD-based outlier clipping.
 * Used to map Boone -> DraftSharks scale per week.
 */
export function robustLinearFit(xs: number[], ys: number[]) {
  const pairs = xs.map((x, i) => ({ x, y: ys[i] })).filter(p => Number.isFinite(p.x) && Number.isFinite(p.y))
  if (pairs.length < 3) return { a: 0, b: 1 }
  const ols = (pts: {x:number,y:number}[]) => {
    const n = pts.length
    const meanX = pts.reduce((s,p)=>s+p.x,0)/n
    const meanY = pts.reduce((s,p)=>s+p.y,0)/n
    const sXX = pts.reduce((s,p)=>s+(p.x-meanX)**2,0)
    const sXY = pts.reduce((s,p)=>s+(p.x-meanX)*(p.y-meanY),0)
    const b = sXX === 0 ? 1 : sXY / sXX
    const a = meanY - b*meanX
    return {a,b}
  }
  let {a,b} = ols(pairs)
  const residuals = pairs.map(p => Math.abs(p.y - (a + b*p.x)))
  const median = (arr:number[]) => [...arr].sort((a,b)=>a-b)[Math.floor(arr.length/2)]
  const mad = median(residuals.map(r => Math.abs(r - median(residuals)))) || 1
  const thresh = median(residuals) + 2.5*mad
  const kept = pairs.filter(p => Math.abs(p.y - (a + b*p.x)) <= thresh)
  if (kept.length >= 3) ({a,b} = ols(kept))
  return { a, b }
}

export function applyScale(a: number, b: number, x: number | null | undefined) {
  if (x == null || !Number.isFinite(x)) return null
  return a + b * x
}
