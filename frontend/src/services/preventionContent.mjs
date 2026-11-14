// Pure helpers shared by the public page, the admin editor and node tests.
// Restricted Markdown: paragraphs, "- " lists, **bold** and [text](https://...).
// Rendering builds React elements from these tokens; HTML is never injected.

export const SECTION_LIMITS = { title: 120, body: 4000, source_label: 200, source_url: 500 }
export const SECTION_SLUG = /^[a-z0-9]+(-[a-z0-9]+)*$/

const HTML_TAG = /<\s*[A-Za-z!/?]/
const HTML_ENTITY = /&(#\d+|#x[0-9a-f]+|[a-z]+);/i
const DANGEROUS_SCHEME = /(javascript|vbscript|data|file):/i
const CONTROL = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/
const LINK = /\[([^\]\n]+)\]\(([^)\s]+)\)/g
const SAFE_URL = /^https:\/\/[^\s<>"'`]+$/
const EMAIL = /[\w.+-]+@[\w-]+\.[\w.-]+/
const DOCUMENT_NUMBER = /\b\d{1,2}\.\d{3}\.\d{3}\b|\b\d{7,8}\b/
const LABELS = { title: 'El título', body: 'El contenido', source_label: 'La fuente', source_url: 'El enlace de la fuente' }

export function safeUrl(url) {
  return typeof url === 'string' && SAFE_URL.test(url) ? url : null
}

// Mirrors backend/app/prevention.py so the editor can warn before saving.
// The server remains the authority and rejects anything this misses.
export function validateSectionField(field, value, { required = false } = {}) {
  const label = LABELS[field]
  const text = String(value ?? '').trim()
  if (!text) return required ? `${label} es obligatorio.` : ''
  if (text.length > SECTION_LIMITS[field]) return `${label} supera ${SECTION_LIMITS[field]} caracteres.`
  if (CONTROL.test(text)) return `${label} contiene caracteres de control no permitidos.`
  if (HTML_TAG.test(text) || HTML_ENTITY.test(text)) return `${label} no admite HTML; usá texto o el Markdown permitido.`
  if (DANGEROUS_SCHEME.test(text.replace(/\s+/g, ''))) return `${label} contiene un enlace o esquema no permitido.`
  if (field === 'source_url') return safeUrl(text) ? '' : `${label} sólo admite enlaces https://.`
  for (const [, , url] of text.matchAll(LINK)) if (!safeUrl(url)) return `${label} sólo admite enlaces https://.`
  if (EMAIL.test(text) || DOCUMENT_NUMBER.test(text)) return `${label} parece incluir datos personales; el contenido preventivo debe ser general.`
  return ''
}

export function validateSection(section) {
  const errors = {}
  for (const field of ['title', 'body', 'source_label', 'source_url']) {
    const message = validateSectionField(field, section[field], { required: field === 'title' || field === 'body' })
    if (message) errors[field] = message
  }
  return errors
}

function parseInline(text) {
  const tokens = []
  let last = 0
  const pattern = /\*\*([^*\n]+)\*\*|\[([^\]\n]+)\]\(([^)\s]+)\)/g
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) tokens.push({ type: 'text', text: text.slice(last, match.index) })
    if (match[1] !== undefined) tokens.push({ type: 'strong', text: match[1] })
    else {
      const href = safeUrl(match[3])
      tokens.push(href ? { type: 'link', text: match[2], href } : { type: 'text', text: match[0] })
    }
    last = match.index + match[0].length
  }
  if (last < text.length) tokens.push({ type: 'text', text: text.slice(last) })
  return tokens
}

export function parseRestrictedMarkdown(source) {
  const blocks = []
  const chunks = String(source ?? '').replace(/\r\n?/g, '\n').split(/\n\s*\n/)
  for (const chunk of chunks) {
    const lines = chunk.split('\n').map(line => line.trim()).filter(Boolean)
    if (!lines.length) continue
    if (lines.every(line => line.startsWith('- '))) {
      blocks.push({ type: 'list', items: lines.map(line => parseInline(line.slice(2).trim())) })
    } else {
      blocks.push({ type: 'paragraph', inline: parseInline(lines.join(' ')) })
    }
  }
  return blocks
}

const NATION = {
  prevention: 'https://www.argentina.gob.ar/como-prevenir-el-dengue',
  symptoms: 'https://www.argentina.gob.ar/sintomas-y-signos-de-alarma',
  fumigation: 'https://www.argentina.gob.ar/node/371159',
}

// Static fallback: same slugs/titles as backend/app/prevention_seed.py.
export function legacySections(content) {
  const sources = new Map((content.sources || []).map(source => [source.url, source]))
  const bullets = items => items.map(item => `- ${item}`).join('\n')
  const rows = [
    ['prevencion', 'Prevenir empieza por eliminar criaderos', bullets(content.prevention), 10, NATION.prevention],
    ['control-vectorial', content.vector_control.title, content.vector_control.body, 20, NATION.fumigation],
    ['sintomas', 'Síntomas compatibles', bullets(content.symptoms), 30, NATION.symptoms],
    ['consejos-medicos', 'Qué hacer ante síntomas', content.medical_advice.join('\n\n'), 40, NATION.symptoms],
    ['signos-alarma', 'Signos de alarma', bullets(content.warning_signs), 50, NATION.symptoms],
  ]
  return rows.map(([slug, title, body, position, url]) => {
    const source = sources.get(url)
    return {
      slug, title, body, position,
      source_label: source ? `${source.title} · ${source.publisher}` : null,
      source_url: source ? url : null,
      version: null, published_at: content.published_at || null,
    }
  })
}

function validPublicSection(section) {
  return section && typeof section.slug === 'string' && SECTION_SLUG.test(section.slug)
    && typeof section.title === 'string' && typeof section.body === 'string'
    && Number.isInteger(section.position)
}

// Returns sections from the API, or null when the static fallback must be used.
export function publicSectionsFrom(payload) {
  if (payload?.schema_version !== 'prevention-sections/1' || !Array.isArray(payload.sections)) return null
  if (payload.initialized !== true) return null
  if (!payload.sections.every(validPublicSection)) return null
  return [...payload.sections].sort((a, b) => a.position - b.position || a.slug.localeCompare(b.slug))
}

export function sectionsBySlug(sections) {
  return Object.fromEntries(sections.map(section => [section.slug, section]))
}

export const KNOWN_SLUGS = ['prevencion', 'control-vectorial', 'sintomas', 'consejos-medicos', 'signos-alarma']
