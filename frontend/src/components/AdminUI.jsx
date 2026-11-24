import { Link } from 'react-router-dom'
import { Icon } from './AdminLayout'
import './AdminUI.css'

// Shared building blocks of the Administración v2 screens (docs/diseno/admin-v2): screen header,
// card, badge, notice, button/link and table. Presentation only: no data, no requests.

const UI_ICONS = {
  lock: 'M6 10h12a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2zM8 10V7a4 4 0 0 1 8 0v3',
  info: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01',
  warning: 'M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01',
}

const join = (...names) => names.filter(Boolean).join(' ')

// Screen header: optional breadcrumb, title, subtitle and a badge or actions on the right.
// Keeps the .admin-header hooks shared by every Administración screen (title and subtitle style).
export function ScreenHeader({ breadcrumb, title, subtitle, aside, className }) {
  return <header className={join('admin-header ui-screen-header', className)}>
    <div>
      {breadcrumb && <nav className="ui-breadcrumb" aria-label="Ruta">
        {breadcrumb.map((item, index) => <span key={item.label}>{index > 0 && <span aria-hidden="true"> / </span>}
          {item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}</span>)}
      </nav>}
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
    {aside && <div className="ui-screen-aside">{aside}</div>}
  </header>
}

// Card: a titled surface. `as` keeps the right landmark (section, aside, article, div).
export function Card({ as: Tag = 'section', title, titleId, level = 2, actions, className, children, ...rest }) {
  const Heading = `h${level}`
  return <Tag className={join('ui-card', className)} aria-labelledby={title && titleId ? titleId : undefined} {...rest}>
    {(title || actions) && <div className="ui-card-head">{title && <Heading id={titleId} className="ui-card-title">{title}</Heading>}{actions}</div>}
    {children}
  </Tag>
}

// Badge: short status text; tone sets the colours (all AA on their background).
export function Badge({ tone = 'neutral', icon, className, children }) {
  return <span className={join('ui-badge', `ui-tone-${tone}`, className)}>{icon && <Icon d={icon} size={14}/>}{children}</span>
}

// Notice: a highlighted explanation (protected mode, warnings). role defaults to "note".
export function Notice({ tone = 'warn', icon = UI_ICONS.lock, role = 'note', className, children }) {
  return <div className={join('ui-notice', `ui-notice-${tone}`, className)} role={role}>
    {icon && <Icon d={icon} size={18}/>}<div>{children}</div>
  </div>
}

// Button or link with the same look (44 px target). `to` renders a router link.
export function UiButton({ to, variant = 'secondary', className, children, ...rest }) {
  const classes = join('ui-button', `ui-button-${variant}`, className)
  return to ? <Link className={classes} to={to} {...rest}>{children}</Link> : <button type="button" className={classes} {...rest}>{children}</button>
}

// Table with the shared look; wide content scrolls inside its own box, never the page.
export function UiTable({ className, caption, children, ...rest }) {
  return <div className="ui-table-scroll"><table className={join('ui-table', className)} {...rest}>
    {caption && <caption>{caption}</caption>}{children}
  </table></div>
}
