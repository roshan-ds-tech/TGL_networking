import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import './index.css'
import { useState, useEffect, lazy, Suspense } from 'react'
import App from './App.jsx'
// The member app is a separate chunk: visitors to the marketing page never
// download it.
const ProductApp = lazy(() => import('./ProductApp.jsx'))
import NotFound from './pages/NotFound.jsx'

const container = document.getElementById('root')

const PRODUCT_EXACT = ['/login', '/signup', '/verify-email', '/forgot-password', '/reset-password']
const isUnder = (path, prefix) => path === prefix || path.startsWith(`${prefix}/`)
const isProductPath = (path) => PRODUCT_EXACT.includes(path) || isUnder(path, '/app') || isUnder(path, '/onboarding')
// The marketing site is a single page; its sections are #anchors.
const isMarketingPath = (path) => path === '/' || path === '/index.html'

function Router() {
  const [path, setPath] = useState(window.location.pathname)
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  
  if (isProductPath(path)) {
    return (
      <Suspense fallback={<div style={{ minHeight: '100vh', background: '#F6EEDF' }} aria-busy="true" />}>
        <ProductApp />
      </Suspense>
    )
  }
  if (isMarketingPath(path)) return <App />
  return <NotFound />
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
if (container.hasChildNodes() && isMarketingPath(window.location.pathname)) {
  hydrateRoot(container, tree)
} else {
  // The prerendered markup is the marketing page. Any other route (member
  // app, 404) renders a different tree, so hydrating would be a mismatch —
  // discard the markup and render fresh.
  container.replaceChildren()
  createRoot(container).render(tree)
}
