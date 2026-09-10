/* Build-time prerender: inject real HTML into dist/index.html.
 *
 * Runs after the normal client build. Renders the app to a string via the SSR
 * bundle and substitutes it into the empty #root div, so the deployed HTML
 * contains the actual page content instead of <div id="root"></div>.
 *
 * The client still hydrates the same React tree over it (see src/main.jsx),
 * so behaviour and appearance are unchanged — this only affects what a crawler
 * that does not run JavaScript can read.
 */
import { readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const indexPath = resolve(root, 'dist/index.html');
const ssrEntry = resolve(root, 'dist-ssr/entry-server.js');

if (!existsSync(indexPath)) {
  throw new Error('dist/index.html not found — run the client build first.');
}
if (!existsSync(ssrEntry)) {
  throw new Error('dist-ssr/entry-server.js not found — run the SSR build first.');
}

const { render } = await import(pathToFileURL(ssrEntry).href);
const html = render();

if (!html || html.length < 1000) {
  // A near-empty render means the tree failed to render rather than that the
  // page is small. Fail loudly instead of shipping a blank page.
  throw new Error(`Prerender produced suspiciously little markup (${html?.length ?? 0} chars).`);
}

const template = readFileSync(indexPath, 'utf8');
const marker = '<div id="root"></div>';
if (!template.includes(marker)) {
  throw new Error(`Could not find ${marker} in dist/index.html.`);
}

writeFileSync(indexPath, template.replace(marker, `<div id="root">${html}</div>`), 'utf8');

// The SSR bundle is a build artefact, not something to deploy.
rmSync(resolve(root, 'dist-ssr'), { recursive: true, force: true });

console.log(`prerender: injected ${html.length.toLocaleString()} chars into dist/index.html`);
