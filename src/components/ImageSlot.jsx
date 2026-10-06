import { useEffect, useState } from 'react';

/* Stand-in for the design source's <image-slot> element.
 *
 * The prototype (TGL Product Platform.dc.html) uses a custom element that lets
 * you drag an image onto a placeholder box. Nothing in the product uploads or
 * serves member/provider imagery yet, so rendering that box as a real <img>
 * would show a broken image. This keeps the exact same footprint — every call
 * site passes the same width/height/shape the prototype used, so the
 * surrounding layout is unchanged — and fills it with the initial, which is
 * what the rest of the app already does for avatars.
 */

const SHAPES = {
  circle: () => ({ borderRadius: '50%' }),
  rounded: (radius) => ({ borderRadius: radius }),
  rect: () => ({ position: 'absolute', inset: 0, borderRadius: 0, width: '100%', height: '100%' }),
};

export default function ImageSlot({
  shape = 'rect',
  radius = 16,
  initial,
  label,
  fontSize,
  style = {},
  src,
}) {
  const glyph = (initial || '').trim().charAt(0).toUpperCase();
  // A member's uploaded photo, when there is one; the initial otherwise (and
  // as the fallback if the image can't load).
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  const showPhoto = !!src && !failed;

  return (
    <span
      aria-hidden="true"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
        overflow: 'hidden',
        background: 'linear-gradient(140deg, rgba(224,181,88,0.28), rgba(192,141,46,0.14))',
        border: '1px solid rgba(192,141,46,0.35)',
        color: 'rgba(43,23,64,0.72)',
        fontWeight: 800,
        letterSpacing: '-0.02em',
        lineHeight: 1,
        ...SHAPES[shape](radius),
        ...style,
      }}
    >
      {showPhoto ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
          style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
        />
      ) : glyph ? (
        <span style={{ fontSize: fontSize || 'clamp(18px, 40%, 56px)' }}>{glyph}</span>
      ) : (
        <span
          style={{
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: '.16em',
            textTransform: 'uppercase',
            color: 'rgba(43,23,64,0.42)',
          }}
        >
          {label}
        </span>
      )}
    </span>
  );
}
