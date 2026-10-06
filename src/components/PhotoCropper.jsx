import { useEffect, useRef, useState } from 'react';

/* Circular photo cropper — the "move and scale" step of social-media avatar
   uploads. The preview and the exported image are drawn from the same math on
   a canvas, so what sits inside the circle is exactly what gets saved.

   Drag to reposition, slider / mouse wheel / pinch-less +/- to zoom. The image
   can never be moved or zoomed so far that the circle shows empty space. */

const VIEW = 280; // CSS px of the square viewport the circle is inscribed in
const OUT = 512; // exported edge, matches what the server stores
const MAX_ZOOM = 4;

export default function PhotoCropper({ file, onCancel, onSave }) {
  const canvasRef = useRef(null);
  const drag = useRef(null);
  const [bitmap, setBitmap] = useState(null);
  const [error, setError] = useState('');
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 }); // image centre vs. viewport centre, CSS px
  const [saving, setSaving] = useState(false);

  // Decode once. 'from-image' applies the EXIF rotation phones write.
  useEffect(() => {
    let alive = true;
    let bmp = null;
    createImageBitmap(file, { imageOrientation: 'from-image' })
      .then((b) => {
        bmp = b;
        if (alive) setBitmap(b);
        else b.close?.();
      })
      .catch(() => alive && setError("That image couldn't be opened. Try a different photo."));
    return () => {
      alive = false;
      bmp?.close?.();
    };
  }, [file]);

  const base = bitmap ? VIEW / Math.min(bitmap.width, bitmap.height) : 1; // "cover" scale
  const scale = base * zoom;

  function clamp(o, s = scale) {
    if (!bitmap) return o;
    const mx = Math.max(0, (bitmap.width * s - VIEW) / 2);
    const my = Math.max(0, (bitmap.height * s - VIEW) / 2);
    return { x: Math.min(mx, Math.max(-mx, o.x)), y: Math.min(my, Math.max(-my, o.y)) };
  }

  function changeZoom(next) {
    const z = Math.min(MAX_ZOOM, Math.max(1, next));
    setZoom(z);
    setOffset((o) => clamp(o, base * z)); // re-clamp so zooming out can't expose edges
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !bitmap) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = VIEW * dpr;
    canvas.height = VIEW * dpr;
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, VIEW, VIEW);
    const w = bitmap.width * scale;
    const h = bitmap.height * scale;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(bitmap, VIEW / 2 + offset.x - w / 2, VIEW / 2 + offset.y - h / 2, w, h);
  }, [bitmap, scale, offset]);

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape' && !saving) onCancel(); };
    window.addEventListener('keydown', onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prev;
    };
  }, [onCancel, saving]);

  function down(e) {
    if (!bitmap) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { x: e.clientX, y: e.clientY, o: offset };
  }
  function move(e) {
    const d = drag.current;
    if (!d) return;
    setOffset(clamp({ x: d.o.x + e.clientX - d.x, y: d.o.y + e.clientY - d.y }));
  }
  function up() {
    drag.current = null;
  }
  function wheel(e) {
    e.preventDefault();
    changeZoom(zoom - e.deltaY * 0.0025);
  }
  function key(e) {
    const step = 12;
    const d = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] }[e.key];
    if (!d) return;
    e.preventDefault();
    setOffset((o) => clamp({ x: o.x + d[0], y: o.y + d[1] }));
  }

  // The viewport element needs a non-passive wheel listener to stop page scroll.
  const frameRef = useRef(null);
  useEffect(() => {
    const el = frameRef.current;
    if (!el) return;
    el.addEventListener('wheel', wheel, { passive: false });
    return () => el.removeEventListener('wheel', wheel);
  });

  async function save() {
    if (!bitmap || saving) return;
    setSaving(true);
    try {
      const out = document.createElement('canvas');
      out.width = OUT;
      out.height = OUT;
      const ctx = out.getContext('2d');
      ctx.imageSmoothingQuality = 'high';
      const sw = VIEW / scale; // the square of the source image inside the viewport
      const sx = bitmap.width / 2 - offset.x / scale - sw / 2;
      const sy = bitmap.height / 2 - offset.y / scale - sw / 2;
      ctx.drawImage(bitmap, sx, sy, sw, sw, 0, 0, OUT, OUT);
      const blob = await new Promise((resolve) => out.toBlob(resolve, 'image/jpeg', 0.92));
      if (!blob) throw new Error('Could not prepare the photo.');
      await onSave(blob);
    } catch {
      setSaving(false); // caller shows the error; stay open so the crop isn't lost
    }
  }

  return (
    <div className="pc-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget && !saving) onCancel(); }}>
      <div className="pc-dialog" role="dialog" aria-modal="true" aria-labelledby="pc-title">
        <h2 id="pc-title">Adjust your photo</h2>
        <p className="pc-sub">Drag to reposition. Use the slider to zoom.</p>

        {error ? (
          <p className="pc-error">{error}</p>
        ) : (
          <div
            ref={frameRef}
            className="pc-frame"
            style={{ width: VIEW, height: VIEW }}
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
            onPointerCancel={up}
            onKeyDown={key}
            tabIndex={0}
            aria-label="Photo crop area. Use arrow keys to move the image."
          >
            <canvas ref={canvasRef} style={{ width: VIEW, height: VIEW }} />
            <span className="pc-mask" />
            {!bitmap && <span className="pc-loading">Loading…</span>}
          </div>
        )}

        {!error && (
          <div className="pc-zoom">
            <button type="button" aria-label="Zoom out" onClick={() => changeZoom(zoom - 0.25)} disabled={!bitmap}>−</button>
            <input
              type="range" min="1" max={MAX_ZOOM} step="0.01" value={zoom} disabled={!bitmap}
              onChange={(e) => changeZoom(Number(e.target.value))} aria-label="Zoom"
            />
            <button type="button" aria-label="Zoom in" onClick={() => changeZoom(zoom + 0.25)} disabled={!bitmap}>+</button>
          </div>
        )}

        <div className="pc-actions">
          <button type="button" className="pf-btn" onClick={onCancel} disabled={saving}>Cancel</button>
          <button type="button" className="pf-btn pf-btn--primary" onClick={save} disabled={!bitmap || saving || !!error}>
            {saving ? 'Saving…' : 'Save photo'}
          </button>
        </div>
      </div>
    </div>
  );
}
