import { createContext } from 'react'

// The page that owns the Administración frame (AdminArea) tells the App to hide the public header
// and footer while AdminLayout is mounted.
export const AdminFrameContext = createContext(() => {})
