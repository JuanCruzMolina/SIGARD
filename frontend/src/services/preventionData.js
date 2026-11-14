import { getPublicPrevention } from './citizenReports'
import { demoMode } from './demoMode'
import { legacySections, publicSectionsFrom } from './preventionContent.mjs'

// A production build without VITE_API_URL (e.g. Vercel frontend only) never
// probes localhost; the page then uses the static JSON directly.
const apiConfigured = demoMode || import.meta.env.DEV || Boolean(import.meta.env.VITE_API_URL)

export const PREVENTION_DATA_ERROR = 'No pudimos cargar la información preventiva. Intentá nuevamente más tarde.'

const DATA_PATHS = {
  content: '/data/prevention_content.json',
  facilities: '/data/health_facilities.geojson',
}

async function getJson(path) {
  const response = await fetch(path, { cache: 'no-cache' })
  if (!response.ok) throw new Error(`No se pudo cargar ${path}`)
  return response.json()
}

function validateFacilities(collection) {
  if (collection?.type !== 'FeatureCollection' || !Array.isArray(collection.features)) {
    throw new Error('Directorio de salud inválido')
  }
  const ids = new Set()
  collection.features.forEach((feature) => {
    const properties = feature.properties || {}
    const coordinates = feature.geometry?.coordinates
    if (
      feature.geometry?.type !== 'Point' || coordinates?.length !== 2 ||
      !Number.isFinite(coordinates[0]) || !Number.isFinite(coordinates[1]) ||
      !properties.id || !properties.name || !['caps', 'hospital'].includes(properties.type) ||
      !properties.source_url || !properties.reviewed_at || ids.has(properties.id)
    ) throw new Error('Establecimiento incompleto o duplicado')
    ids.add(properties.id)
  })
  const caps = collection.features.filter(({ properties }) => properties.type === 'caps').length
  const hospitals = collection.features.filter(({ properties }) => properties.type === 'hospital').length
  if (caps !== 24 || hospitals < 3) throw new Error('El inventario público no está completo')
  return collection
}

// Published sections from the API; any failure silently uses the static JSON.
async function loadSections(content) {
  if (apiConfigured) {
    try {
      const sections = publicSectionsFrom(await getPublicPrevention({ signal: AbortSignal.timeout(4000) }))
      if (sections) return { sections, sectionsSource: 'api' }
    } catch { /* API unavailable: static fallback below, without a visible error. */ }
  }
  return { sections: legacySections(content), sectionsSource: 'static' }
}

export async function loadPreventionData() {
  const [content, facilities] = await Promise.all([
    getJson(DATA_PATHS.content),
    getJson(DATA_PATHS.facilities),
  ])
  if (!content?.prevention?.length || !content?.warning_signs?.length || !content?.sources?.length) {
    throw new Error('Contenido preventivo inválido')
  }
  return { content, facilities: validateFacilities(facilities), ...await loadSections(content) }
}
