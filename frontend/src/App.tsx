import { BrowserRouter, Route, Routes } from 'react-router'
import Layout from './components/Layout'
import RequestDetailPage from './pages/RequestDetailPage'
import RequestsPage from './pages/RequestsPage'
import TesterPage from './pages/TesterPage'
import SessionProvider from './session/SessionProvider'

export default function App() {
  return (
    <SessionProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<TesterPage />} />
            <Route path="requests" element={<RequestsPage />} />
            <Route path="requests/:id" element={<RequestDetailPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </SessionProvider>
  )
}
