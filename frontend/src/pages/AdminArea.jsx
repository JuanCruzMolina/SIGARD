import { useCallback } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { AdminFrameContext } from '../components/adminFrame'
import { ADMIN_HOME } from '../services/adminShell.mjs'
import AdminAuditoria from './AdminAuditoria'
import AdminInicio from './AdminInicio'
import AdminPredictivo from './AdminPredictivo'
import AdminReports from './AdminReports'
import '../Prevention.css'

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
      <Route path="auditoria" element={<AdminAuditoria/>}/>
      <Route path="*" element={<Navigate to={ADMIN_HOME} replace/>}/>
    </Routes>
  </AdminFrameContext.Provider>
}
