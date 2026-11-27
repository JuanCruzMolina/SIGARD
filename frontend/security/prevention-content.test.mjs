// Pure checks for the editable prevention content (no API, browser or private data).
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import { transformWithOxc } from 'vite'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import {
  CONTENT_PENDING, INTRO_SLUGS, KNOWN_SLUGS, legacySections, PAGE_SLUGS, parseRestrictedMarkdown, publicSectionsFrom,
  safeUrl, sectionsBySlug, validateSection, validateSectionField,
} from '../src/services/preventionContent.mjs'

const root = new URL('../../', import.meta.url)
const content = JSON.parse(await readFile(new URL('frontend/public/data/prevention_content.json', root), 'utf8'))

test('static fallback maps the published JSON to the same sections as the backend seed', async () => {
  const sections = legacySections(content)
  assert.deepEqual(sections.map(section => section.slug), KNOWN_SLUGS)
  const seed = await readFile(new URL('backend/app/prevention_seed.py', root), 'utf8')
  for (const section of sections) {
    const title = section.slug === 'control-vectorial' ? 'vector["title"]' : `"${section.title}"`
    assert.ok(seed.includes(`("${section.slug}", ${title},`), `${section.slug} has the same slug/title in the backend seed`)
    assert.ok(safeUrl(section.source_url), `${section.slug} keeps an https health source`)
    assert.deepEqual(validateSection(section), {}, `${section.slug} passes the same validation as admin edits`)
  }
  const prevention = parseRestrictedMarkdown(sectionsBySlug(sections).prevencion.body)
  assert.equal(prevention[0].type, 'list')
  assert.equal(prevention[0].items.length, content.prevention.length)
  const advice = parseRestrictedMarkdown(sectionsBySlug(sections)['consejos-medicos'].body)
  assert.equal(advice.filter(block => block.type === 'paragraph').length, content.medical_advice.length)
})

test('restricted Markdown yields text tokens only and drops unsafe links', () => {
  const blocks = parseRestrictedMarkdown('Primer **párrafo** con [guía](https://example.test/a).\n\n- uno\n- [mal](javascript:alert(1))\n\n<script>x</script>')
  assert.deepEqual(blocks[0].inline.map(token => token.type), ['text', 'strong', 'text', 'link', 'text'])
  assert.equal(blocks[0].inline[3].href, 'https://example.test/a')
  assert.equal(blocks[1].type, 'list')
  assert.ok(blocks[1].items[1].every(token => token.type === 'text'))
  assert.equal(blocks[1].items[1].map(token => token.text).join(''), '[mal](javascript:alert(1))')
  // Raw markup stays inert text; React escapes it when rendering.
  assert.deepEqual(blocks[2], { type: 'paragraph', inline: [{ type: 'text', text: '<script>x</script>' }] })
  assert.equal(safeUrl('http://example.test'), null)
  assert.equal(safeUrl('https://example.test/"onmouseover=x'), null)
})

test('client validation mirrors server rules for HTML, schemes, limits and personal data', () => {
  for (const value of ['<b>x</b>', 'a &lt;b&gt;', '[x](javascript:alert(1))', 'java\nscript:alert(1)', 'x'.repeat(4001), '[x](http://e.test)', 'mail persona@example.test', 'DNI 30.123.456', 'oculto \u0007']) {
    assert.notEqual(validateSectionField('body', value), '', value)
  }
  assert.equal(validateSectionField('body', '- Fiebre de 38 °C o más.\n- Llamá al 107.'), '')
  assert.notEqual(validateSectionField('source_url', 'javascript:alert(1)'), '')
  assert.notEqual(validateSectionField('title', '', { required: true }), '')
  assert.equal(validateSectionField('source_label', ''), '')
})

test('public API payload is accepted only when initialized and well formed', () => {
  const section = { slug: 'b', title: 'B', body: 'x', position: 20, version: 1 }
  const ok = { schema_version: 'prevention-sections/1', initialized: true, sections: [section, { ...section, slug: 'a', position: 10 }] }
  assert.deepEqual(publicSectionsFrom(ok).map(item => item.slug), ['a', 'b'])
  assert.deepEqual(publicSectionsFrom({ ...ok, sections: [] }), [], 'unpublished content stays hidden, no fallback')
  assert.equal(publicSectionsFrom({ ...ok, initialized: false }), null)
  assert.equal(publicSectionsFrom({ ...ok, schema_version: 'other' }), null)
  assert.equal(publicSectionsFrom({ ...ok, sections: [{ ...section, slug: 'Bad Slug' }] }), null)
  assert.equal(publicSectionsFrom(null), null)
})

test('public loader falls back silently and production without API never probes localhost', async () => {
  const loader = await readFile(new URL('frontend/src/services/preventionData.js', root), 'utf8')
  assert.match(loader, /if \(apiConfigured\)/)
  assert.match(loader, /AbortSignal\.timeout\(4000\)/)
  assert.match(loader, /catch \{/)
  assert.match(loader, /legacySections\(content\)/)
  assert.match(loader, /apiConfigured = demoMode \|\| import\.meta\.env\.DEV \|\| Boolean\(import\.meta\.env\.VITE_API_URL\)/)
  for (const file of ['frontend/src/components/RestrictedMarkdown.jsx', 'frontend/src/components/AdminPrevention.jsx', 'frontend/src/pages/Prevencion.jsx']) {
    assert.doesNotMatch(await readFile(new URL(file, root), 'utf8'), /dangerouslySetInnerHTML/, file)
  }
})

test('emergency contacts are marked in the content itself and only those', () => {
  const marked = content.contacts.filter(contact => contact.category === 'emergencia').map(contact => contact.id)
  assert.deepEqual(marked, ['medical-emergency', 'general-emergency'])
  assert.ok(content.contacts.every(contact => contact.category === undefined || contact.category === 'emergencia'))
})

// --- /prevencion: PreventionGuide and SymptomsAlert carry no health sentence of their own.
const COMPONENTS = ['frontend/src/components/PreventionGuide.jsx', 'frontend/src/components/SymptomsAlert.jsx']
// Only labels, the SIGARD scope disclaimer and the call action; every health sentence is published content.
const ALLOWED_TEXT = new Set(['Prevención', 'Síntomas', 'SIGARD brinda orientación general; no realiza diagnósticos.', 'Llamar al'])

function writtenTexts(source) {
  const code = source.split('\n').filter(line => !/^\s*(import|\/\/)/.test(line)).join('\n')
  const jsxText = [...code.matchAll(/>([^<>{}]+)</g)].map(m => m[1].trim())
  const literals = [...code.matchAll(/(['"`])((?:(?!\1)[^\n\\])*)\1/g)].map(m => m[2].trim())
    .filter(text => /\s/.test(text) && !/^[\w-]+( [\w-]+)*$/.test(text) || /[áéíóúñ¿¡]/i.test(text))
  return [...jsxText, ...literals].filter(text => /[A-Za-zÁÉÍÓÚáéíóúñ]/.test(text))
}

test('PreventionGuide and SymptomsAlert write no health sentences in the code', async () => {
  for (const file of COMPONENTS) {
    const source = await readFile(new URL(file, root), 'utf8')
    const extra = writtenTexts(source).filter(text => !ALLOWED_TEXT.has(text))
    assert.deepEqual(extra, [], `${file} has text written in the code; publish it from Administración`)
    assert.doesNotMatch(source, /mosquito|criadero|agua|descacharreo|fiebre|dolor|actuá|revisá|consult|urgente|semana/i, file)
  }
  // The guard itself catches a sentence written in the code (regression for this check).
  assert.deepEqual(writtenTexts('<p>Revisá tu casa cada semana.</p>'), ['Revisá tu casa cada semana.'])
  assert.deepEqual(writtenTexts("const x = 'Sin agua acumulada, no hay ciclo.'"), ['Sin agua acumulada, no hay ciclo.'])
})

// Server render of the two components with generated fictional sections only.
const dataUrl = code => `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
async function loadComponent(file) {
  const target = new URL(file, root)
  let source = (await transformWithOxc(await readFile(target, 'utf8'), target.pathname, { jsx: { runtime: 'automatic' } })).code
  for (const [spec, url] of [
    ['./InfoIcons', new URL('frontend/src/components/InfoIcons.jsx', root)],
    ['./RestrictedMarkdown', new URL('frontend/src/components/RestrictedMarkdown.jsx', root)],
  ]) {
    const code = (await transformWithOxc(await readFile(url, 'utf8'), url.pathname, { jsx: { runtime: 'automatic' } })).code
      .replace(/from\s*(['"])\.\.\/services\/preventionContent\.mjs\1/, `from ${JSON.stringify(new URL('frontend/src/services/preventionContent.mjs', root).href)}`)
      .replace(/from\s*(['"])react\/jsx-runtime\1/, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
    source = source.replace(new RegExp(`from\\s*(['"])${spec.replace('.', '\\.')}\\1`), `from ${JSON.stringify(dataUrl(code))}`)
  }
  source = source.replace(/from\s*(['"])\.\.\/services\/preventionContent\.mjs\1/, `from ${JSON.stringify(new URL('frontend/src/services/preventionContent.mjs', root).href)}`)
    .replace(/from\s*(['"])react\/jsx-runtime\1/, `from ${JSON.stringify(import.meta.resolve('react/jsx-runtime'))}`)
  return (await import(dataUrl(source))).default
}
const fictional = (slug, title = `Título ficticio ${slug}`) => ({ slug, title, body: `Texto ficticio de ${slug}.`, position: 1, source_label: 'Fuente ficticia', source_url: 'https://example.org/f', version: 1 })
const base = Object.fromEntries(KNOWN_SLUGS.map(slug => [slug, fictional(slug)]))

test('/prevencion intro texts: published sections are used; otherwise the pending state', async () => {
  const PreventionGuide = await loadComponent('frontend/src/components/PreventionGuide.jsx')
  const SymptomsAlert = await loadComponent('frontend/src/components/SymptomsAlert.jsx')
  const render = (Component, props) => renderToStaticMarkup(React.createElement(Component, props))
  const pendingGuide = render(PreventionGuide, { sections: base })
  assert.equal(pendingGuide.split(CONTENT_PENDING).length - 1, 1)
  assert.match(pendingGuide, /<div class="prevention-principle"><svg[^>]*>.*?<\/svg><p class="content-pending" role="status">/)
  const pendingSymptoms = render(SymptomsAlert, { sections: base, emergencyNumber: '0000' })
  assert.match(pendingSymptoms, /<h2 id="symptoms-title">Síntomas<\/h2>/)
  assert.equal(pendingSymptoms.split(CONTENT_PENDING).length - 1, 1)

  const sections = { ...base, ...Object.fromEntries(Object.values(INTRO_SLUGS).map(slug => [slug, fictional(slug)])) }
  const guide = render(PreventionGuide, { sections })
  assert.ok(!guide.includes(CONTENT_PENDING))
  assert.match(guide, /<div class="section-intro" data-slug="prevencion-resumen"><p><span>Texto ficticio de prevencion-resumen\.<\/span><\/p><small class="section-source">/)
  assert.match(guide, /<strong>Título ficticio prevencion-principio<\/strong><p><span>Texto ficticio de prevencion-principio\.<\/span><\/p><small class="section-source">Fuente: /)
  const symptoms = render(SymptomsAlert, { sections, emergencyNumber: '0000' })
  assert.ok(!symptoms.includes(CONTENT_PENDING))
  assert.match(symptoms, /<h2 id="symptoms-title">Título ficticio sintomas-encabezado<\/h2>/)
  assert.match(symptoms, /Texto ficticio de sintomas-encabezado\.<\/span><\/p><small class="section-source">/)
  // Reserved intro slugs are not repeated as extra sections on the page.
  assert.ok(Object.values(INTRO_SLUGS).every(slug => PAGE_SLUGS.includes(slug)))
  assert.deepEqual(PAGE_SLUGS.slice(0, KNOWN_SLUGS.length), KNOWN_SLUGS)
  const page = await readFile(new URL('frontend/src/pages/Prevencion.jsx', root), 'utf8')
  assert.match(page, /sections\.filter\(section => !PAGE_SLUGS\.includes\(section\.slug\)\)/)
})
