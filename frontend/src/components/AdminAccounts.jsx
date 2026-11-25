import { useEffect, useRef, useState } from 'react'
import { createAdminAccount, deactivateAdminAccount, listAdminAccounts, rotateAdminPassword } from '../services/citizenReports'
import { Badge, Card, Notice, ScreenHeader, UiButton, UiTable } from './AdminUI'
import './AdminAccounts.css'

const emptyCredentials = { email: '', password: '', confirmation: '', current_password: '', confirmed: false }
const actionLabels = { create: 'Crear cuenta administrativa', rotate: 'Rotar contraseña', deactivate: 'Desactivar cuenta' }
// F6.5 (docs/diseno/admin-v2/Cuentas.dc.html): presentation only. Same requests, confirmations
// (current password + explicit checkbox), last-administrator protection and texts. Passwords are
// never shown, prefilled or kept after a request; the API returns no secret to display.
const ICONS = {
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
  check: 'M5 12l4 4 10-10',
  off: 'M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16zM6.3 6.3l11.4 11.4',
}
const dateText = value => new Date(value).toLocaleDateString('es-AR')
// Long addresses break only before the «@» (no extra text: <wbr> keeps textContent intact).
const emailText = email => { const at = email.indexOf('@'); return at > 0 ? <>{email.slice(0, at)}<wbr/>{email.slice(at)}</> : email }

export default function AdminAccounts({ token, onSessionExpired }) {
  const [listing, setListing] = useState(null)
  const [page, setPage] = useState(1)
  const [attempt, setAttempt] = useState(0)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [action, setAction] = useState(null)
  const [fields, setFields] = useState(emptyCredentials)
  const actionHeading = useRef(null)

  useEffect(() => { if (action) actionHeading.current?.focus() }, [action])

  useEffect(() => {
    let active = true
    listAdminAccounts(token, page)
      .then(result => { if (active) { setListing(result); setLoading(false) } })
      .catch(requestError => {
        if (!active) return
        setLoading(false)
        if (requestError.status === 401) onSessionExpired('La sesión venció o fue revocada. Ingresá nuevamente.')
        else setError(requestError.status ? requestError.message : 'No se pudo conectar con la API administrativa. Intentá nuevamente.')
      })
    return () => { active = false }
  }, [attempt, onSessionExpired, page, token])

  function reload(nextPage = page) {
    setLoading(true); setError(''); setPage(nextPage); setAttempt(value => value + 1)
  }

  function openAction(kind, account = null) {
    setAction({ kind, account }); setFields(emptyCredentials); setError(''); setNotice('')
  }

  function update(event) {
    const { name, value, checked, type } = event.target
    setFields(current => ({ ...current, [name]: type === 'checkbox' ? checked : value }))
  }

  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setError(''); setNotice('')
    if (action.kind !== 'deactivate' && fields.password !== fields.confirmation) {
      setError('La nueva contraseña y su confirmación no coinciden.'); return
    }
    if (!fields.confirmed) { setError('Confirmá la operación antes de continuar.'); return }
    setBusy(true)
    try {
      const authorization = { current_password: fields.current_password }
      let result
      if (action.kind === 'create') result = await createAdminAccount(token, { ...authorization, email: fields.email, password: fields.password })
      else if (action.kind === 'rotate') result = await rotateAdminPassword(token, action.account.id, { ...authorization, new_password: fields.password })
      else result = await deactivateAdminAccount(token, action.account.id, authorization)
      if (action.kind !== 'create' && result.id === listing.current_user_id) {
        onSessionExpired(action.kind === 'rotate' ? 'Contraseña actualizada. Ingresá con la nueva contraseña.' : 'Tu cuenta fue desactivada y la sesión se cerró.')
        return
      }
      setNotice(action.kind === 'create' ? 'Cuenta administrativa creada.' : action.kind === 'rotate' ? 'Contraseña actualizada. Las sesiones anteriores de esa cuenta quedaron invalidadas.' : 'Cuenta desactivada. Sus sesiones anteriores quedaron invalidadas.')
      setAction(null); reload()
    } catch (requestError) {
      if (requestError.status === 401) onSessionExpired('La sesión venció o fue revocada. Ingresá nuevamente.')
      else setError(requestError.status ? requestError.message : 'No se pudo conectar con la API administrativa. Revisá la conexión e intentá nuevamente.')
    } finally {
      setFields(current => ({ ...emptyCredentials, email: current.email })); setBusy(false)
    }
  }

  const disabled = busy || loading
  return <main className="admin-page admin-accounts">
    <ScreenHeader breadcrumb={[{ label: 'Inicio', to: '/admin/inicio' }, { label: 'Cuentas' }]} title="Cuentas administrativas"
      subtitle="Acceso exclusivo de administradores autorizados."
      aside={<UiButton variant="primary" disabled={disabled || !listing} onClick={() => openAction('create')}>Crear cuenta</UiButton>} />
    <Notice tone="info" icon={ICONS.info} className="account-policy"><p>Cada cambio requiere tu contraseña actual y una confirmación. Debe quedar al menos una cuenta administrativa activa.</p></Notice>
    {notice && <Notice tone="info" icon={ICONS.check} role="status" className="account-notice"><p>{notice}</p></Notice>}
    {error && <Notice tone="danger" icon={null} role="alert" className="form-error"><p>{error}</p></Notice>}
    <div className="admin-accounts-grid">
      <Card className="account-list" title="Cuentas y estado" titleId="accounts-title" aria-busy={loading}>
        {loading && <p role="status">Consultando cuentas administrativas…</p>}
        {!loading && !listing && <UiButton onClick={() => reload()}>Reintentar carga</UiButton>}
        {listing && <>
          <p className="account-count">{listing.active_admin_count} {listing.active_admin_count === 1 ? 'cuenta administrativa activa' : 'cuentas administrativas activas'} · {listing.total} {listing.total === 1 ? 'cuenta en total' : 'cuentas en total'}</p>
          <UiTable className="accounts-table" role="table">
            <thead><tr><th scope="col">Correo</th><th scope="col">Estado</th><th scope="col">Creada</th><th scope="col">Acciones</th></tr></thead>
            <tbody>{listing.items.map(account => <tr key={account.id} data-account={account.id}>
              <th scope="row"><span className="account-email">{emailText(account.email)}</span>{account.id === listing.current_user_id && <Badge tone="neutral" className="account-self">Tu cuenta</Badge>}</th>
              <td><span className="account-state-label">Estado: </span>{account.active ? <Badge tone="ok" icon={ICONS.check} className="account-state">Activa</Badge> : <Badge tone="neutral" icon={ICONS.off} className="account-state">Inactiva</Badge>}</td>
              <td><span className="account-state-label">Creada: </span><time dateTime={account.created_at}>{dateText(account.created_at)}</time></td>
              <td>{account.active ? <div className="account-actions">
                <UiButton disabled={disabled} onClick={() => openAction('rotate', account)} aria-label={`Rotar contraseña de ${account.email}`}>Rotar contraseña</UiButton>
                <UiButton className="account-danger" disabled={disabled || listing.active_admin_count <= 1} onClick={() => openAction('deactivate', account)} aria-label={`Desactivar ${account.email}`}>Desactivar</UiButton>
              </div> : <span className="account-none">Sin acciones</span>}</td>
            </tr>)}</tbody>
          </UiTable>
          {!listing.items.length && <p>No hay cuentas en esta página. Volvé a la página anterior.</p>}
          <div className="account-pagination"><UiButton disabled={disabled || page <= 1} onClick={() => reload(page - 1)}>Anterior</UiButton><span>Página <span className="mono">{page}</span></span><UiButton disabled={disabled || page * listing.page_size >= listing.total} onClick={() => reload(page + 1)}>Siguiente</UiButton></div>
        </>}
      </Card>
      <Card className="account-operation" aria-labelledby="account-action-title">
        <h2 id="account-action-title" className="ui-card-title" ref={actionHeading} tabIndex="-1">{action ? actionLabels[action.kind] : 'Gestionar una cuenta'}</h2>
        {!action ? <p>Creá una cuenta o elegí una acción del listado. Las contraseñas no se muestran ni se recuperan: un administrador autorizado puede establecer una nueva.</p> : <form className="admin-update" onSubmit={submit}>
          {action.account && <p className="account-target">Cuenta: <strong>{action.account.email}</strong>{action.account.id === listing.current_user_id && <span>Estás modificando tu propia cuenta.</span>}</p>}
          {action.kind === 'create' && <label>Correo de la nueva cuenta<input type="email" name="email" value={fields.email} onChange={update} required minLength="5" maxLength="150" autoComplete="off" disabled={busy}/></label>}
          {action.kind !== 'deactivate' && <>
            <label>Nueva contraseña<input type="password" name="password" value={fields.password} onChange={update} required minLength="8" maxLength="200" autoComplete="new-password" disabled={busy}/><small>Entre 8 y 200 caracteres. Para una rotación debe ser distinta de la anterior.</small></label>
            <label>Confirmar nueva contraseña<input type="password" name="confirmation" value={fields.confirmation} onChange={update} required minLength="8" maxLength="200" autoComplete="new-password" disabled={busy}/></label>
          </>}
          {action.kind !== 'create' && <Notice tone={action.kind === 'deactivate' ? 'danger' : 'warn'} className="account-warning"><p>{action.kind === 'deactivate' ? 'La cuenta dejará de poder ingresar.' : 'La contraseña anterior dejará de funcionar.'} Se invalidarán todos sus tokens anteriores. {action.account.id === listing.current_user_id && 'Esta operación cerrará tu sesión.'}</p></Notice>}
          <label>Tu contraseña actual<input type="password" name="current_password" value={fields.current_password} onChange={update} required minLength="8" maxLength="200" autoComplete="current-password" disabled={busy}/></label>
          <label className="account-confirm"><input type="checkbox" name="confirmed" checked={fields.confirmed} onChange={update} required disabled={busy}/><span>Confirmo que quiero {action.kind === 'create' ? 'otorgar permisos administrativos a esta cuenta' : action.kind === 'deactivate' ? 'desactivar esta cuenta y cerrar sus sesiones' : 'cambiar la contraseña y cerrar las sesiones de esta cuenta'}.</span></label>
          <div className="account-actions"><UiButton type="submit" variant="primary" className={action.kind === 'deactivate' ? 'account-submit-danger' : undefined} disabled={disabled}>{busy ? 'Guardando…' : actionLabels[action.kind]}</UiButton><UiButton disabled={busy} onClick={() => { setAction(null); setFields(emptyCredentials); setError('') }}>Cancelar</UiButton></div>
        </form>}
      </Card>
    </div>
  </main>
}
