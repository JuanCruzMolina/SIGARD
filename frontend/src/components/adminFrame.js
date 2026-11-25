import { createContext } from 'react'

// The page that owns the Administración frame (AdminArea) tells the App to hide the public header
// and footer while AdminLayout is mounted.
export const AdminFrameContext = createContext(() => {})

// AdminLayout gives its screens a way to ask for the side-menu counters again right after a change
// (an alert decided, a report status saved). It only repeats the requests the counters already use.
export const AdminCountersContext = createContext(() => {})
