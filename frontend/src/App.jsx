import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Mapa from './pages/Mapa'
import Admin from './pages/Admin'
import Info from './pages/Info'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Mapa />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/info" element={<Info />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
