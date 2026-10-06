import { useEffect, useRef, useState } from 'react';
import ImageSlot from './ImageSlot';
import { photoError, PHOTO_TYPES } from '../lib/photo';

/* Profile photo control: round preview + Add / Change / Remove.
 *
 *   value     — current photo URL (server) or null
 *   onPick    — async (file) => void; may upload immediately (dashboard) or
 *               just keep the file for later (signup, before the account exists)
 *   onRemove  — async () => void
 *   pending   — a picked-but-not-uploaded File, previewed locally */
export default function PhotoPicker({ value, initial, onPick, onRemove, pending = null, size = 84, hint }) {
  const input = useRef(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!pending) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(pending);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [pending]);

  async function choose(ev) {
    const file = ev.target.files?.[0];
    ev.target.value = ''; // allow picking the same file again
    if (!file) return;
    const problem = photoError(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError('');
    setBusy(true);
    try {
      await onPick(file);
    } catch (err) {
      setError(err?.message || 'Could not upload the photo. Please try again.');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setError('');
    setBusy(true);
    try {
      await onRemove();
    } catch (err) {
      setError(err?.message || 'Could not remove the photo.');
    } finally {
      setBusy(false);
    }
  }

  const shown = preview || value;
  const btn = { padding: '9px 16px', borderRadius: 999, fontSize: 11.5, fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', cursor: busy ? 'default' : 'pointer', whiteSpace: 'nowrap' };

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
      <ImageSlot shape="circle" label="Photo" initial={initial} src={shown} style={{ width: size, height: size }} fontSize={Math.round(size * 0.36)} />
      <div style={{ minWidth: 0 }}>
        <p style={{ margin: '0 0 8px', fontSize: 14, fontWeight: 700, color: '#2B1740' }}>Profile photo <span style={{ fontWeight: 500, color: 'rgba(43,23,64,0.65)' }}>· optional</span></p>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="tglp-ghost" disabled={busy} onClick={() => input.current?.click()} style={{ ...btn, border: '1px solid rgba(53,26,78,0.3)', background: 'transparent', color: '#35194E' }}>
            {busy ? 'Saving…' : shown ? 'Change photo' : 'Add photo'}
          </button>
          {shown && onRemove && (
            <button type="button" disabled={busy} onClick={remove} style={{ ...btn, border: 'none', background: 'transparent', color: '#8E3B3B' }}>
              Remove
            </button>
          )}
        </div>
        <p role={error ? 'alert' : undefined} style={{ margin: '8px 0 0', fontSize: 12.5, color: error ? '#9A2B2B' : 'rgba(43,23,64,0.65)' }}>
          {error || hint || 'PNG, JPG or WEBP. Shown to TGL members on your profile.'}
        </p>
        <input ref={input} type="file" accept={PHOTO_TYPES.join(',')} onChange={choose} hidden />
      </div>
    </div>
  );
}
