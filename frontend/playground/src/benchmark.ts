type Case = { id: string; recall: number | null; reciprocal_rank: number | null;
  returned_no_evidence: boolean; latency_ms: number }
export type BenchmarkReport = {
  mode: string; dataset_version: string; model: string; index: string; dimensions: number
  top_k: number; min_score: number; case_count: number; answerable_count: number
  recall_at_k: number | null; mrr_at_k: number | null; cases: Case[]
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function finite(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}
function count(value: unknown): value is number {
  return finite(value) && Number.isInteger(value)
}
function score(value: unknown): value is number | null {
  return value === null || (finite(value) && value <= 1)
}
function isCase(value: unknown): value is Case {
  return record(value) && typeof value.id === 'string' && score(value.recall) &&
    score(value.reciprocal_rank) && typeof value.returned_no_evidence === 'boolean' && finite(value.latency_ms)
}

export function parseBenchmark(text: string): BenchmarkReport {
  const value: unknown = JSON.parse(text)
  if (!record(value) || typeof value.mode !== 'string' || typeof value.dataset_version !== 'string' ||
    typeof value.model !== 'string' || typeof value.index !== 'string' || !count(value.dimensions) ||
    !count(value.top_k) || value.top_k < 1 || !finite(value.min_score) || value.min_score > 1 ||
    !count(value.case_count) || !count(value.answerable_count) || value.answerable_count > value.case_count ||
    !score(value.recall_at_k) || !score(value.mrr_at_k) || !Array.isArray(value.cases) ||
    value.cases.length !== value.case_count || !value.cases.every(isCase) ||
    new Set(value.cases.map(item => item.id)).size !== value.case_count) {
    throw new Error('This file does not match the retrieval evaluator report format.')
  }
  return value as BenchmarkReport
}
