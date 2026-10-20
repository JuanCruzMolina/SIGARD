import { useEffect, useRef, useState } from 'react'
import { createAdminAccount, deactivateAdminAccount, listAdminAccounts, rotateAdminPassword } from '../services/citizenReports'

const emptyCredentials = { email: '', password: '', confirmation: '', current_password: '', confirmed: false }
const actionLabels = { create: 'Crear cuenta administrativa', rotate: 'Rotar contraseña', deactivate: 'Desactivar cuenta' }

export default function AdminAccounts({ token, onBack, onLogout, onSessionExpired }) {
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
    <header className="admin-header"><div><h1>Cuentas administrativas</h1><p>Acceso exclusivo de administradores autorizados.</p></div><div><button type="button" className="secondary-button" onClick={onBack}>Volver a reportes</button><button type="button" className="text-button" onClick={onLogout}>Cerrar sesión</button></div></header>
    <p className="account-policy">Cada cambio requiere tu contraseña actual y una confirmación. Debe quedar al menos una cuenta administrativa activa.</p>
    {notice && <p className="account-notice" role="status">{notice}</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
    <div className="admin-accounts-grid">
      <section className="panel account-list" aria-labelledby="accounts-title" aria-busy={loading}>
        <div className="account-list-heading"><h2 id="accounts-title">Cuentas y estado</h2><button type="button" className="primary-button" disabled={disabled || !listing} onClick={() => openAction('create')}>Crear cuenta</button></div>
        {loading && <p role="status">Consultando cuentas administrativas…</p>}
        {!loading && !listing && <button type="button" className="secondary-button" onClick={() => reload()}>Reintentar carga</button>}
        {listing && <>
          <p>{listing.active_admin_count} {listing.active_admin_count === 1 ? 'cuenta administrativa activa' : 'cuentas administrativas activas'} · {listing.total} {listing.total === 1 ? 'cuenta en total' : 'cuentas en total'}</p>
          <div className="table-scroll"><table role="table"><thead><tr><th scope="col">Correo</th><th scope="col">Estado</th><th scope="col">Acciones</th></tr></thead><tbody>{listing.items.map(account => <tr key={account.id}>
            <th scope="row">{account.email}{account.id === listing.current_user_id && <small>Tu cuenta</small>}</th>
            <td><span className="account-state-label">Estado: </span>{account.active ? 'Activa' : 'Inactiva'}</td>
            <td><div className="account-actions"><button type="button" className="secondary-button" disabled={disabled || !account.active} onClick={() => openAction('rotate', account)} aria-label={`Rotar contraseña de ${account.email}`}>Rotar contraseña</button><button type="button" className="text-button" disabled={disabled || !account.active || listing.active_admin_count <= 1} onClick={() => openAction('deactivate', account)} aria-label={`Desactivar ${account.email}`}>Desactivar</button></div></td>
          </tr>)}</tbody></table></div>
          {!listing.items.length && <p>No hay cuentas en esta página. Volvé a la página anterior.</p>}
          <div className="account-pagination"><button type="button" className="secondary-button" disabled={disabled || page <= 1} onClick={() => reload(page - 1)}>Anterior</button><span>Página {page}</span><button type="button" className="secondary-button" disabled={disabled || page * listing.page_size >= listing.total} onClick={() => reload(page + 1)}>Siguiente</button></div>
        </>}
      </section>
      <section className="panel account-operation" aria-labelledby="account-action-title">
        <h2 id="account-action-title" ref={actionHeading} tabIndex="-1">{action ? actionLabels[action.kind] : 'Gestionar una cuenta'}</h2>
        {!action ? <p>Creá una cuenta o elegí una acción del listado. Las contraseñas no se muestran ni se recuperan: un administrador autorizado puede establecer una nueva.</p> : <form className="admin-update" onSubmit={submit}>
          {action.account && <p className="account-target">Cuenta: <strong>{action.account.email}</strong>{action.account.id === listing.current_user_id && <span>Estás modificando tu propia cuenta.</span>}</p>}
          {action.kind === 'create' && <label>Correo de la nueva cuenta<input type="email" name="email" value={fields.email} onChange={update} required minLength="5" maxLength="150" autoComplete="off" disabled={busy}/></label>}
          {action.kind !== 'deactivate' && <>
            <label>Nueva contraseña<input type="password" name="password" value={fields.password} onChange={update} required minLength="8" maxLength="200" autoComplete="new-password" disabled={busy}/><small>Entre 8 y 200 caracteres. Para una rotación debe ser distinta de la anterior.</small></label>
            <label>Confirmar nueva contraseña<input type="password" name="confirmation" value={fields.confirmation} onChange={update} required minLength="8" maxLength="200" autoComplete="new-password" disabled={busy}/></label>
          </>}
          {action.kind !== 'create' && <p>{action.kind === 'deactivate' ? 'La cuenta dejará de poder ingresar.' : 'La contraseña anterior dejará de funcionar.'} Se invalidarán todos sus tokens anteriores. {action.account.id === listing.current_user_id && 'Esta operación cerrará tu sesión.'}</p>}
          <label>Tu contraseña actual<input type="password" name="current_password" value={fields.current_password} onChange={update} required minLength="8" maxLength="200" autoComplete="current-password" disabled={busy}/></label>
          <label className="account-confirm"><input type="checkbox" name="confirmed" checked={fields.confirmed} onChange={update} required disabled={busy}/><span>Confirmo que quiero {action.kind === 'create' ? 'otorgar permisos administrativos a esta cuenta' : action.kind === 'deactivate' ? 'desactivar esta cuenta y cerrar sus sesiones' : 'cambiar la contraseña y cerrar las sesiones de esta cuenta'}.</span></label>
          <div className="account-actions"><button type="submit" className="primary-button" disabled={disabled}>{busy ? 'Guardando…' : actionLabels[action.kind]}</button><button type="button" className="secondary-button" disabled={busy} onClick={() => { setAction(null); setFields(emptyCredentials); setError('') }}>Cancelar</button></div>
        </form>}
      </section>
    </div>
  </main>
}
