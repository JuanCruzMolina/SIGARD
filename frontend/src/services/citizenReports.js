import { demoMode } from './demoMode'

const API_URL = (demoMode ? 'http://127.0.0.1:8766' : import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function apiRequest(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options, cache: 'no-store', credentials: 'omit',
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('No pudimos conectar con el servicio. Revisá la conexión e intentá nuevamente.', { cause: error })
  }
  const contentType = response.headers.get('content-type') || ''
  const body = contentType.includes('application/json') ? await response.json() : null
  if (!response.ok) {
    const detail = body?.detail
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg).join(' · ')
      : detail || 'No se pudo completar la operación.'
    const error = new Error(message)
    error.status = response.status
    throw error
  }
  return body
}

export function createCitizenReport(payload, idempotencyKey) {
  return apiRequest('/api/v1/citizen-reports', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify(payload),
  })
}

export function getCitizenReportStatus(trackingCode, options = {}) {
  return apiRequest(`/api/v1/citizen-reports/status/${encodeURIComponent(trackingCode.trim().toUpperCase())}`, options)
}

export function geocodeAddress(addressReference, options = {}) {
  return apiRequest('/api/v1/geocoding/address', {
    ...options, method: 'POST',
    body: JSON.stringify({ address_reference: addressReference }),
  })
}

export function adminLogin(credentials, options = {}) {
  return apiRequest('/api/v1/admin/session', { ...options, method: 'POST', body: JSON.stringify(credentials) })
}

export function demoWorkspaceRequest(token, path, options = {}) {
  if (!demoMode) return Promise.reject(new Error('Este espacio ficticio sólo funciona con npm run dev:demo.'))
  return apiRequest(`/api/v1/admin/demo${path}`, { ...options, headers: adminHeaders(token) })
}

function adminHeaders(token) {
  return { Authorization: `Bearer ${token}` }
}

function filterQuery(filters) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => value && query.set(key, value))
  return query
}

export function listAdminReports(token, filters = {}, options = {}) {
  return apiRequest(`/api/v1/admin/citizen-reports?${filterQuery(filters)}`, { ...options, headers: adminHeaders(token) })
}

export function getAdminReport(token, reportId, options = {}) {
  return apiRequest(`/api/v1/admin/citizen-reports/${reportId}`, { ...options, headers: adminHeaders(token) })
}

export function updateAdminReport(token, reportId, changes, options = {}) {
  return apiRequest(`/api/v1/admin/citizen-reports/${reportId}`, {
    ...options, method: 'PATCH', headers: adminHeaders(token), body: JSON.stringify(changes),
  })
}

export function listAdminAccounts(token, page = 1) {
  return apiRequest(`/api/v1/admin/users?page=${page}`, { headers: adminHeaders(token) })
}

export function createAdminAccount(token, payload) {
  return apiRequest('/api/v1/admin/users', {
    method: 'POST', headers: adminHeaders(token), body: JSON.stringify(payload),
  })
}

export function deactivateAdminAccount(token, id, payload) {
  return apiRequest(`/api/v1/admin/users/${id}/deactivate`, {
    method: 'POST', headers: adminHeaders(token), body: JSON.stringify(payload),
  })
}

export function rotateAdminPassword(token, id, payload) {
  return apiRequest(`/api/v1/admin/users/${id}/password`, {
    method: 'POST', headers: adminHeaders(token), body: JSON.stringify(payload),
  })
}

export async function downloadAdminExport(token, filters = {}, options = {}) {
  const response = await fetch(`${API_URL}/api/v1/admin/citizen-reports/export.csv?${filterQuery(filters)}`, {
    ...options, headers: adminHeaders(token), cache: 'no-store', credentials: 'omit',
  })
  if (!response.ok) {
    const error = new Error('No se pudo descargar la exportación.')
    error.status = response.status
    throw error
  }
  const blob = await response.blob()
  options.signal?.throwIfAborted()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'sigard-reportes.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}
