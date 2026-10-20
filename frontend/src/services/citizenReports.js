const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
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

export function getCitizenReportStatus(trackingCode) {
  return apiRequest(`/api/v1/citizen-reports/status/${encodeURIComponent(trackingCode.trim())}`)
}

export function geocodeAddress(addressReference) {
  return apiRequest('/api/v1/geocoding/address', {
    method: 'POST',
    body: JSON.stringify({ address_reference: addressReference }),
  })
}

export function adminLogin(credentials) {
  return apiRequest('/api/v1/admin/session', { method: 'POST', body: JSON.stringify(credentials) })
}

function adminHeaders(token) {
  return { Authorization: `Bearer ${token}` }
}

export function listAdminReports(token, filters = {}) {
  const query = new URLSearchParams()
  Object.entries(filters).forEach(([key, value]) => value && query.set(key, value))
  return apiRequest(`/api/v1/admin/citizen-reports?${query}`, { headers: adminHeaders(token) })
}

export function getAdminReport(token, reportId) {
  return apiRequest(`/api/v1/admin/citizen-reports/${reportId}`, { headers: adminHeaders(token) })
}

export function updateAdminReport(token, reportId, changes) {
  return apiRequest(`/api/v1/admin/citizen-reports/${reportId}`, {
    method: 'PATCH', headers: adminHeaders(token), body: JSON.stringify(changes),
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

export async function downloadAdminExport(token) {
  const response = await fetch(`${API_URL}/api/v1/admin/citizen-reports/export.csv`, {
    headers: adminHeaders(token),
  })
  if (!response.ok) {
    const error = new Error('No se pudo descargar la exportación.')
    error.status = response.status
    throw error
  }
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'sigard-reportes.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}
