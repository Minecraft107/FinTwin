// Run with `npm test` (Node's built-in test runner, no extra dependency).
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { assetLabel, inr, inrCompact, monthLabel, pct, signed, titleCase, today } from './format.js'

test('inr uses Indian digit grouping and handles missing values', () => {
  assert.equal(inr(130000), '₹1,30,000')
  assert.equal(inr(12345678), '₹1,23,45,678')
  assert.equal(inr(null), '—')
  assert.equal(inr(Number.NaN), '—')
})

test('inrCompact picks K / L / Cr units', () => {
  assert.equal(inrCompact(950), '₹950')
  assert.equal(inrCompact(45000), '₹45K')
  assert.equal(inrCompact(130000), '₹1.3L')
  assert.equal(inrCompact(24000000), '₹2.4Cr')
  assert.equal(inrCompact(-130000), '-₹1.3L')
  assert.equal(inrCompact(null), '—')
})

test('pct and signed', () => {
  assert.equal(pct(0.1684), '16.8%')
  assert.equal(pct(null), '—')
  assert.equal(signed(500), '+₹500')
  assert.equal(signed(-500), '-₹500')
})

test('labels', () => {
  assert.match(monthLabel('2026-09-30'), /^Sept? 26$/) // ICU spells September "Sep" or "Sept"
  assert.equal(monthLabel('2026-09-30'), monthLabel('2026-09'))
  assert.equal(titleCase('large_purchase'), 'Large purchase')
  assert.equal(assetLabel('ppf'), 'PPF')
  assert.equal(assetLabel('real_estate'), 'Real estate')
})

test('today is the local calendar date, not the UTC one', () => {
  const justAfterMidnight = new Date(2026, 9, 9, 0, 30) // local time
  assert.equal(today(justAfterMidnight), '2026-10-09')
})
