import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import './index.css'
import { useState, useEffect } from 'react'
import App from './App.jsx'
import ProductApp from './ProductApp.jsx'

const container = document.getElementById('root')

function Router() {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  
  const isProductApp = ['/login', '/signup', '/verify-email', '/forgot-password', '/reset-password'].includes(path) || path.startsWith('/app') || path.startsWith('/onboarding')
  return isProductApp ? <ProductApp /> : <App />
}

const tree = (
  <StrictMode>
    <Router />
  </StrictMode>
)

/* Production builds ship prerendered markup inside #root (see
   scripts/prerender.mjs). Hydrate that rather than createRoot, which would
   throw the server HTML away and re-render from scratch — a visible flash and
   a wasted render. Dev has no prerender step, so #root is empty there and the
   normal client render still applies. */
if (container.hasChildNodes()) {
  hydrateRoot(container, tree)
} else {
  createRoot(container).render(tree)
}
