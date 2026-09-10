/* Server entry, used only by the build-time prerender step.
 *
 * The site is a client-rendered SPA, so the HTML it shipped contained nothing
 * but an empty #root. Googlebot executes JavaScript and coped, but most AI
 * search crawlers (OAI-SearchBot, PerplexityBot, ClaudeBot and friends) do
 * not — to them the page was blank. Rendering the same component tree to a
 * string at build time gives those crawlers the real content, while the
 * browser hydrates over identical markup so nothing changes visually.
 *
 * renderToString is used deliberately rather than snapshotting a headless
 * browser: the reveal-on-scroll effect sets opacity:0 on mount, so a browser
 * snapshot would bake invisible content into the HTML. Effects never run
 * during renderToString, so what is captured here is the true pre-effect
 * markup — exactly what the client renders on its first pass.
 */
import { StrictMode } from 'react';
import { renderToString } from 'react-dom/server';
import App from './App.jsx';

export function render() {
  return renderToString(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
