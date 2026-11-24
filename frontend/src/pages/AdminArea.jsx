import { useCallback, useEffect, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import AdminLayout from '../components/AdminLayout'
import { AdminFrameContext } from '../components/adminFrame'
import AdminLoginForm from '../components/AdminLoginForm'
import { ADMIN_HOME } from '../services/adminShell.mjs'
import { endSession, readSession, sessionExpired } from '../services/adminSession.mjs'
import AdminInicio from './AdminInicio'
import AdminPredictivo from './AdminPredictivo'
import AdminReports from './AdminReports'
import '../Prevention.css'

const EXPIRED = 'La sesión venció. Ingresá nuevamente.'
const SOON = {
  auditoria: { title: 'Auditoría', text: 'Registro de acciones administrativas.', soon: 'La consulta de auditoría todavía no tiene pantalla propia. Las decisiones sobre alertas siguen registradas en Alertas internas › Auditoría.' },
}

// Sections without their own screen yet: same session rules as the other screens.
function AdminSoon({ section }) {
  const [token, setToken] = useState(() => { const stored = readSession(); return stored && !sessionExpired(stored) ? stored : '' })
  const [notice, setNotice] = useState(() => readSession() && !token ? EXPIRED : '')
  // An expired token found on arrival is removed with the email kept for the top bar.
  useEffect(() => { if (!token && readSession()) endSession() }, [token])
  const copy = SOON[section]
  if (!token) return <AdminLoginForm title="Administración" description="Acceso restringido a personal autorizado." notice={notice} onLogin={setToken}/>
  return <AdminLayout active={section} token={token} onLogout={() => { endSession(); setToken(''); setNotice('') }} onExpire={() => { setToken(''); setNotice(EXPIRED) }}>
    <main className="admin-page"><header className="admin-header"><div><h1>{copy.title}</h1><p>{copy.text}</p></div></header>
      <section className="admin-soon" aria-labelledby="admin-soon-title"><h2 id="admin-soon-title">Próximamente</h2><p>{copy.soon}</p></section>
    </main>
  </AdminLayout>
}

// Administración v2 (F4): /admin/* routes inside the frame. /admin leads to /admin/inicio and the
// old /admin/reportes keeps working. Each screen keeps its own session handling and its login
// keeps the URL, so logging in without a requested route lands on /admin/inicio (F5) and a
// requested route (for example /admin/cuentas) is respected.
export default function AdminArea({ onFrameChange }) {
  const setFrame = useCallback(value => onFrameChange?.(value), [onFrameChange])
  return <AdminFrameContext.Provider value={setFrame}>
    <Routes>
      <Route index element={<Navigate to={ADMIN_HOME} replace/>}/>
      <Route path="inicio" element={<AdminInicio/>}/>
      <Route path="predictivo" element={<AdminPredictivo/>}/>
      <Route path="alertas" element={<AdminReports key="alertas" section="alertas"/>}/>
      <Route path="reportes" element={<AdminReports key="reportes" section="reportes"/>}/>
      <Route path="contenido" element={<AdminReports key="contenido" section="contenido"/>}/>
      <Route path="cuentas" element={<AdminReports key="cuentas" section="cuentas"/>}/>
      <Route path="auditoria" element={<AdminSoon section="auditoria"/>}/>
      <Route path="*" element={<Navigate to={ADMIN_HOME} replace/>}/>
    </Routes>
  </AdminFrameContext.Provider>
}
