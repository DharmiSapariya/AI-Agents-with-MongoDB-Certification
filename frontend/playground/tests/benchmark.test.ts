import assert from 'node:assert/strict'
import test from 'node:test'
import { comparisonIssue, parseBenchmark } from '../src/benchmark.ts'

const report = {
  mode: 'live_atlas', dataset_version: '1', model: 'example-model', index: 'example-index',
  dimensions: 1024, top_k: 5, min_score: 0, case_count: 1, answerable_count: 0,
  recall_at_k: null, mrr_at_k: null, cases: [{
    id: 'unanswerable', recall: null, reciprocal_rank: null, returned_no_evidence: true, latency_ms: 12,
  }],
}

test('imports evaluator metadata and preserves missing scores', () => {
  assert.deepEqual(parseBenchmark(JSON.stringify(report)), report)
})

test('rejects unsupported formats, inconsistent counts, and out-of-range scores', () => {
  for (const value of [{ scores: [] }, { ...report, case_count: 3 }, { ...report, recall_at_k: 1.2 }]) {
    assert.throws(() => parseBenchmark(JSON.stringify(value)), /report format/)
  }
})

test('imports recorded failures without treating them as measured abstentions', () => {
  const failed = { ...report, strategy: 'agent', run_id: 'abc', failed_cases: 1,
    cases: [{ ...report.cases[0], returned_no_evidence: null, error: 'timeout' }] }
  assert.deepEqual(parseBenchmark(JSON.stringify(failed)), failed)
})

test('only compares reports with matching datasets, settings and case IDs', () => {
  const run = { ...report, dataset_sha256: 'a'.repeat(64), strategy: 'vector' }
  assert.equal(comparisonIssue(run, { ...run, strategy: 'agent' }), null)
  assert.match(comparisonIssue(run, report) ?? '', /dataset hash/)
  assert.match(comparisonIssue(run, { ...run, top_k: 10 }) ?? '', /settings/)
  assert.match(comparisonIssue(run, { ...run, cases: [{ ...run.cases[0], id: 'other' }] }) ?? '', /different evaluation cases/)
})
