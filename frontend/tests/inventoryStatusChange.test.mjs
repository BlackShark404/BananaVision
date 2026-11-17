import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFile } from 'node:fs/promises'
import { transform } from 'esbuild'

const source = await readFile(new URL('../src/lib/inventoryStatusChange.ts', import.meta.url), 'utf8')
const { code } = await transform(source, { loader: 'ts', format: 'esm' })
const { inventoryStatusChangeNote } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)

const RECORDED = 'This change will be recorded in the scan history.'
const RETURNS = 'The scan returns to stock. If its delivery intake is depleted, the intake reopens.'

test('the status dialog note says what the change does and never calls a status permanent', () => {
  const cases = [
    ['In Stock', 'Sold', `The scan leaves stock. ${RECORDED}`],
    ['In Stock', 'Spoiled', `The scan leaves stock. ${RECORDED}`],
    ['In Stock', 'For Processing', `The scan leaves stock. ${RECORDED}`],
    ['For Processing', 'In Stock', `${RETURNS} ${RECORDED}`],
    ['For Processing', 'Sold', RECORDED],
    ['For Processing', 'Spoiled', RECORDED],
    ['Spoiled', 'For Processing', `This corrects the Spoiled status. ${RECORDED}`],
    ['Spoiled', 'Sold', `This corrects the Spoiled status. ${RECORDED}`],
    ['Spoiled', 'In Stock', `This corrects the Spoiled status. ${RETURNS} ${RECORDED}`],
    ['Sold', 'Spoiled', `This corrects the Sold status. ${RECORDED}`],
    ['Sold', 'For Processing', `This corrects the Sold status. ${RECORDED}`],
    ['Sold', 'In Stock', `This corrects the Sold status. ${RETURNS} ${RECORDED}`],
  ]
  for (const [current, target, note] of cases) {
    assert.equal(inventoryStatusChangeNote(current, target), note, `${current} -> ${target}`)
    assert.doesNotMatch(note, /terminal|cannot be|undone|permanent/i)
  }
})

test('after a reload shows the scan already has the chosen status, the note says nothing changes', () => {
  for (const status of ['In Stock', 'For Processing', 'Sold', 'Spoiled']) {
    assert.equal(inventoryStatusChangeNote(status, status), `The scan is already ${status}. Saving changes nothing.`)
  }
})
