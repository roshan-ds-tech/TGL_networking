import { StrictMode } from 'react'
import { createRoot, hydrateRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

const container = document.getElementById('root')

const tree = (
  <StrictMode>
    <App />
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
