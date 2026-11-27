// Public home page (Situación actual): helpers and server render with generated fictional data only.
// No real package, prevention file or cartography is read here.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithOxc } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import {
  activityState, calendarPeaks, emergencyContact, EMPTY, FICTIONAL_NOTICE, isFictional, longDate, publishedContacts,
  rangeLabel, recentWeeks, seasonCalendar, valueDisplay, weeklyTrend,
} from '../src/services/publicHome.mjs'

const DAY = 86400000
const iso = ms => new Date(ms).toISOString().slice(0, 10)

// Generated fictional package: consecutive weeks from a Sunday, 4 weeks per period; null = "<5".
function fictionalActivity(valuesByYear, { fictional = true, hidden = [] } = {}) {
  const blocks = []
  for (const [year, values] of Object.entries(valuesByYear)) {
    let start = Date.UTC(Number(year), 0, 7)
    for (let b = 0; b * 4 < values.length; b++) {
      const city = values.slice(b * 4, b * 4 + 4).map((value, i) => {
        const week = { year: Number(year), week: b * 4 + i + 1, start: iso(start), end: iso(start + 6 * DAY), value, display: value === null ? '<5' : null }
        if (hidden.includes(`${year}-${week.week}`)) Object.assign(week, { value: null, display: 'oculto' })
        start += 7 * DAY
        return week
      })
      blocks.push({ id: `${year}-B${String(b + 1).padStart(2, '0')}`, year: Number(year), weeks: city.map(w => w.week), start: city[0].start, end: city.at(-1).end, radios: {}, city_weeks: city })
    }
  }
  return {
    schema: 'sigard-public-activity/1', blocks, generated_at: '2030-01-01',
    period: { start: blocks[0].start, end: blocks.at(-1).end, first_block: blocks[0].id, last_block: blocks.at(-1).id },
    source: fictional ? { kind: 'fixture', fictional: true, label: 'Datos ficticios de prueba' } : { kind: 'real', fictional: false, label: 'Fuente ficticia de prueba' },
  }
}

const fictionalContent = (emergencyStatus = 'publicado') => ({
  emergency_number: '0000',
  contacts: [
    { id: 'fict-emergency', label: 'Emergencia ficticia', number_display: '0000', number_tel: '0000', purpose: 'Contacto ficticio.', source_url: 'https://example.org/a', reviewed_at: '2030-01-01', status: emergencyStatus },
    { id: 'fict-office', label: 'Oficina ficticia', number_display: '(0000) 000-001', number_tel: '+00000000001', purpose: 'Consultas ficticias.', source_url: 'https://example.org/b', reviewed_at: '2030-01-02', status: 'publicado' },
    { id: 'fict-pending', label: 'Línea ficticia por confirmar', number_display: '0800-000-0000', number_tel: '08000000000', purpose: 'Sin confirmar.', source_url: 'https://example.org/c', reviewed_at: '2030-01-03', status: 'vigencia_por_confirmar' },
  ],
  sources: [{ title: 'Fuente ficticia', publisher: 'Editor ficticio', url: 'https://example.org/fuente' }],
})
const section = (slug, position) => ({ slug, title: `Título ficticio ${slug}`, body: `- Texto ficticio de ${slug}`, position, source_label: 'Fuente ficticia', source_url: 'https://example.org/s', version: 1 })
const ALL_SLUGS = ['prevencion', 'control-vectorial', 'sintomas', 'consejos-medicos', 'signos-alarma']
const prevention = ({ slugs = ALL_SLUGS, emergencyStatus } = {}) => ({ status: 'ready', data: { content: fictionalContent(emergencyStatus), sections: slugs.map((slug, i) => section(slug, i)) } })

test('date labels are plain language, never "SE" nor block numbers', () => {
  assert.equal(longDate('2024-06-15'), '15 de junio de 2024')
  assert.equal(rangeLabel('2024-06-02', '2024-06-08'), 'del 2 al 8 de junio de 2024')
  assert.equal(rangeLabel('2024-05-26', '2024-06-01'), 'del 26 de mayo al 1 de junio de 2024')
  assert.equal(rangeLabel('2024-01-07', '2024-02-03', { withYear: false }), 'del 7 de enero al 3 de febrero')
  assert.equal(rangeLabel('2019-12-29', '2020-01-25', { withYear: false }), 'del 29 de diciembre de 2019 al 25 de enero de 2020')
  const calendar = seasonCalendar(fictionalActivity({ 2030: [9, 9, 9, 9, 9, 9, 9, 9] }))
  for (const period of calendar.years[0].periods) assert.match(period.label, /^del \d+ de [a-z]+ al \d+ de [a-z]+$/)
  assert.ok(!JSON.stringify(calendar).match(/"label":"[^"]*(SE|[Bb]loque)/))
})

test('protected values are never turned into numbers', () => {
  assert.deepEqual(valueDisplay(7), { known: true, text: '7 registros' })
  assert.deepEqual(valueDisplay(null, '<5'), { known: false, text: 'Menos de 5' })
  assert.deepEqual(valueDisplay(null, 'oculto'), { known: false, text: 'Dato protegido' })
  const weeks = recentWeeks(fictionalActivity({ 2030: [5, 6, null, 8, 9, 10, 11, null, 13, 14] }))
  assert.equal(weeks.length, 8)
  assert.deepEqual(weeks.map(w => w.value), [null, 8, 9, 10, 11, null, 13, 14])
  assert.ok(weeks.every(w => w.known === Number.isInteger(w.value)))
  assert.equal(weeks[0].text, 'Menos de 5')
})

test('trend: only with 8 consecutive visible weeks; otherwise an honest message', () => {
  const trend = values => weeklyTrend(recentWeeks(fictionalActivity({ 2030: values })))
  assert.equal(trend([10, 10, 10, 10, 20, 20, 20, 20]).kind, 'up')
  assert.equal(trend([20, 20, 20, 20, 10, 10, 10, 10]).kind, 'down')
  assert.equal(trend([10, 10, 10, 10, 11, 10, 10, 10]).kind, 'flat')
  assert.match(trend([10, 10, 10, 10, 20, 20, 20, 20]).text, /^80 registros en las últimas 4 semanas, frente a 40 registros en las 4 anteriores\.$/)
  const protectedTrend = trend([10, 10, null, 10, 20, 20, 20, 20])
  assert.equal(protectedTrend.kind, 'unavailable')
  assert.match(protectedTrend.text, /sin revelar valores protegidos/)
  assert.equal(trend([10, 10, 10]).kind, 'unavailable')
  // 2022 is excluded from the package: weeks across the gap are not consecutive.
  const gap = recentWeeks(fictionalActivity({ 2021: [9, 9, 9, 9], 2023: [9, 9, 9, 9] }))
  assert.equal(weeklyTrend(gap).kind, 'unavailable')
})

test('calendar: a period total exists only when every week is visible; peaks come from data', () => {
  const calendar = seasonCalendar(fictionalActivity({ 2030: [5, 6, 7, 8, 30, null, 9, 9, 40, 40, 40, 40] }, { hidden: ['2030-12'] }))
  const [a, b, c] = calendar.years[0].periods
  assert.equal(a.total, 26); assert.equal(a.text, '26 registros')
  assert.equal(b.total, null); assert.equal(b.text, 'Incluye semanas con menos de 5')
  assert.equal(c.total, null); assert.equal(c.text, 'Dato protegido')
  assert.equal(calendar.max, 26)
  assert.match(calendarPeaks(calendar), /^Los períodos con más registros fueron: del 7 de enero al 3 de febrero de 2030 \(26 registros\)\.$/)
  assert.equal(calendarPeaks(seasonCalendar(fictionalActivity({ 2030: [null, 5, 5, 5] }))), '')
  // A period across the new year names each year once (regression: "… de 2021 de 2020").
  const crossing = { blocks: [{ id: 'x', year: 2030, start: '2030-12-29', end: '2031-01-25', city_weeks: [{ start: '2030-12-29', end: '2031-01-04', value: 9 }] }] }
  assert.equal(calendarPeaks(seasonCalendar(crossing)), 'Los períodos con más registros fueron: del 29 de diciembre de 2030 al 25 de enero de 2031 (9 registros).')
})

test('contacts and the emergency number are shown only when published or confirmed', () => {
  assert.deepEqual(publishedContacts(fictionalContent()).map(c => c.id), ['fict-emergency', 'fict-office'])
  assert.equal(emergencyContact(fictionalContent('publicado')).number_display, '0000')
  assert.equal(emergencyContact(fictionalContent('confirmado')).number_display, '0000')
  assert.equal(emergencyContact(fictionalContent('vigencia_por_confirmar')), null)
  assert.equal(emergencyContact({ ...fictionalContent(), emergency_number: '9999' }), null)
  assert.equal(emergencyContact({}), null)
})

test('activity state and fixture detection', () => {
  assert.deepEqual(activityState({ enabled: false }), { status: 'disabled' })
  assert.deepEqual(activityState({ enabled: false, unavailable: true }), { status: 'unavailable' })
  const activity = fictionalActivity({ 2030: [9, 9, 9, 9] })
  assert.deepEqual(activityState({ enabled: true, activity }), { status: 'ready', activity })
  assert.equal(isFictional(activity), true)
  assert.equal(isFictional(fictionalActivity({ 2030: [9] }, { fictional: false })), false)
  assert.equal(isFictional({ source: { kind: 'fixture' } }), true)
})

// --- Server render of the real page component, with only the data loader stubbed.
const dataUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
const stubs = { '../services/preventionData': dataUrl('export const loadPreventionData=()=>new Promise(()=>{});') }
const loaded = new Map()
async function load(file) {
  if (loaded.has(file.href)) return loaded.get(file.href)
  let source = await readFile(file, 'utf8')
  if (file.pathname.endsWith('.jsx')) source = (await transformWithOxc(source, file.pathname, { jsx: { runtime: 'automatic' } })).code
  const pattern = /((?:from|import)\s*)(['"])([^'"]+)\2/g
  const targets = {}
  for (const [, , , spec] of source.matchAll(pattern)) {
    if (spec in targets) continue
    if (stubs[spec]) targets[spec] = stubs[spec]
    else if (!spec.startsWith('.')) targets[spec] = import.meta.resolve(spec)
    else if (spec.endsWith('.css')) targets[spec] = dataUrl('')
    else {
      const target = new URL(/\.[a-z]+$/.test(spec) ? spec : `${spec}.jsx`, file)
      targets[spec] = target.pathname.endsWith('.jsx') ? await load(target) : target.href
    }
  }
  const url = dataUrl(source.replace(pattern, (match, prefix, quote, spec) => prefix + JSON.stringify(targets[spec])))
  loaded.set(file.href, url)
  return url
}
const { HomeView } = await import(await load(new URL('../src/pages/Dashboard.jsx', import.meta.url)))
const render = props => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(HomeView, props)))
const count = (html, text) => html.split(text).length - 1

test('home: three accesses and all seven blocks, without prediction, simulation, ranking or model names', () => {
  const html = render({ prevention: prevention(), activity: { status: 'ready', activity: fictionalActivity({ 2030: [9, 9, 9, 9, 9, 9, 9, 9] }) } })
  assert.match(html, /<a href="\/prevencion#prevenir"[^>]*>.*Cómo prevenir<\/a>/)
  assert.match(html, /<a href="\/prevencion#reportar"[^>]*>.*Reportar un posible criadero<\/a>/)
  assert.match(html, /<a href="\/mapa"[^>]*>.*Ver el mapa<\/a>/)
  for (const id of ['situacion', 'hoy', 'sintomas', 'reporte', 'calendario', 'sobre']) assert.match(html, new RegExp(`<section[^>]*id="${id}"`))
  assert.doesNotMatch(html, /predic|simulaci|percentil|ranking|rf_|modelo|Random|radio censal/i)
  for (const slug of ALL_SLUGS) assert.match(html, new RegExp(`data-slug="${slug}"`))
  assert.equal(count(html, 'Fuente: <a href="https://example.org/s"'), ALL_SLUGS.length)
})

test('home with the fictional package: visible "Datos ficticios de demostración" in situation and calendar', () => {
  const activity = fictionalActivity({ 2029: [5, 6, 7, 8, 9, 10, 11, 12], 2030: [9, null, 9, 9, 20, 20, 20, 20] })
  const html = render({ prevention: prevention(), activity: { status: 'ready', activity } })
  assert.equal(count(html, `data-testid="fictional-notice"`), 2)
  assert.equal(count(html, `${FICTIONAL_NOTICE}.`), 2)
  assert.match(html, /Datos hasta el 3 de marzo de 2030\.<\/strong> Es una reconstrucción histórica: no muestra la situación actual\./)
  assert.match(html, /Menos de 5/)
  assert.doesNotMatch(html, />&lt;5</)
  assert.match(html, /sin revelar valores protegidos/)
  assert.match(html, /2022 no se incluye/)
  // Protected rows carry no bar at all (regression: an unsized bar filled the whole track).
  for (const row of html.match(/<li class="protected">.*?<\/li>/g)) assert.doesNotMatch(row, /bar-fill/)
  assert.equal(count(html, 'class="bar-fill"'), count(html, '<li class="">'))
  // A package that is not a fixture never carries the notice.
  const real = render({ prevention: prevention(), activity: { status: 'ready', activity: fictionalActivity({ 2030: [9, 9, 9, 9] }, { fictional: false }) } })
  assert.equal(count(real, 'data-testid="fictional-notice"'), 0)
  assert.doesNotMatch(real, /ficticios de demostración/)
})

test('home empty states: no package, no API, no published content', () => {
  const disabled = render({ prevention: prevention({ slugs: [] }), activity: { status: 'disabled' } })
  assert.ok(disabled.includes(EMPTY.activityDisabled))
  assert.ok(disabled.includes(EMPTY.calendarDisabled))
  assert.equal(count(disabled, EMPTY.content), 2)
  assert.doesNotMatch(disabled, /data-testid="(fictional-notice|data-date|trend)"/)
  const unavailable = render({ prevention: { status: 'error' }, activity: { status: 'unavailable' } })
  assert.equal(count(unavailable, EMPTY.activityUnavailable), 2)
  assert.ok(unavailable.includes(EMPTY.contentError))
  assert.doesNotMatch(unavailable, /data-testid="emergency-call"/)
  const loading = render({ prevention: { status: 'loading' }, activity: { status: 'loading' } })
  assert.match(loading, /Cargando el resumen de registros/)
})

test('home emergency number follows the contacts rule', () => {
  const published = render({ prevention: prevention({ emergencyStatus: 'publicado' }), activity: { status: 'disabled' } })
  assert.match(published, /<a class="home-call" data-testid="emergency-call" href="tel:0000">/)
  assert.match(published, /Oficina ficticia/)
  assert.doesNotMatch(published, /Línea ficticia por confirmar|0800-000-0000/)
  const pending = render({ prevention: prevention({ emergencyStatus: 'vigencia_por_confirmar' }), activity: { status: 'disabled' } })
  assert.doesNotMatch(pending, /data-testid="emergency-call"|tel:0000"|Emergencia ficticia/)
  const none = render({ prevention: { status: 'ready', data: { content: { ...fictionalContent(), contacts: [] }, sections: [] } }, activity: { status: 'disabled' } })
  assert.ok(none.includes(EMPTY.contacts))
})

test('home source writes no health advice, phone numbers or MVP layers', async () => {
  for (const path of ['../src/pages/Dashboard.jsx', '../src/services/publicHome.mjs']) {
    const source = await readFile(new URL(path, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /fiebre|aspirina|ibuprofeno|paracetamol|dolor|vómito|sangrado|automedic|\b107\b|\b911\b|\d{3}-\d{4}/i, path)
    assert.doesNotMatch(source, /sigardData|SigardComponents|TopRadios|StatCard|predicted_cases|percentile|temporal_predictions|experimental_spatial/, path)
  }
})
