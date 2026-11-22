import { useEffect, useRef, useState } from 'react'
import { ShieldIcon } from './InfoIcons'
import { adminLogin } from '../services/citizenReports'
import { SESSION_KEY } from '../services/adminSession.mjs'

// Administración login shared by /admin/reportes and /admin/predictivo. It stores the session
// token in sessionStorage (same key as before F3) and hands it to the page that rendered it,
// so the page stays on its own route after logging in.
export default function AdminLoginForm({ title, description, notice, onLogin }) {
  const [credentials, setCredentials] = useState({ email: '', password: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const request = useRef(null)
  useEffect(() => () => request.current?.abort(), [])

  async function login(event) {
    event.preventDefault()
    request.current?.abort()
    const current = new AbortController(); request.current = current
    setLoading(true); setError(''); setSubmitted(true)
    try {
      const result = await adminLogin(credentials, { signal: current.signal })
      if (!current.signal.aborted) { sessionStorage.setItem(SESSION_KEY, result.access_token); onLogin(result.access_token) }
    } catch (requestError) { if (!current.signal.aborted) setError(requestError.message) }
    finally { if (!current.signal.aborted) { setLoading(false); setCredentials({ email: '', password: '' }) } }
  }

  return <main className="admin-login-page"><form className="admin-login" onSubmit={login}><ShieldIcon className="admin-shield"/><h1>{title}</h1><p>{description}</p>{notice && !submitted && <p role="status">{notice}</p>}<label>Correo institucional<input type="email" value={credentials.email} onChange={(event) => setCredentials({ ...credentials, email: event.target.value })} required maxLength="150" autoComplete="username"/></label><label>Contraseña<input type="password" value={credentials.password} onChange={(event) => setCredentials({ ...credentials, password: event.target.value })} required minLength="8" maxLength="200" autoComplete="current-password"/></label>{error && <p className="form-error" role="alert">{error}</p>}<button className="primary-button" disabled={loading}>{loading ? 'Ingresando…' : 'Ingresar'}</button></form></main>
}
