// Pure checks for the editable prevention content (no API, browser or private data).
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'
import {
  KNOWN_SLUGS, legacySections, parseRestrictedMarkdown, publicSectionsFrom,
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
