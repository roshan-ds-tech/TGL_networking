// Shared by the Sponsors section and the logo marquee band, so the sponsor
// list only needs to be edited in one place.
//
//   maxHeight     — the large Sponsors-section card
//   marqueeHeight — the compact logo card in the marquee band
//
// marqueeHeight is derived rather than guessed. Each file wraps its artwork
// in a different amount of blank canvas, so scaling them all to the same
// height makes some look far bigger than others. Measuring the ink (the
// non-white bounding box) as a fraction of the canvas gives:
//
//   Shami Equibooks  595x169 canvas, ink 88% of height
//   Creme Bliss      500x500 canvas, ink 60%
//   Saffron          800x800 canvas, ink 41%
//   SkyKeen          640x640 canvas, ink 38%
//
// Dividing a ~30px target by those fractions gives the heights below, so all
// four render with roughly 30px of actual logo regardless of their padding.
export const SPONSORS = [
  { name: 'Shami Equibooks', file: '/images/sponsor_shamiequibooks.png', maxHeight: '54px', marqueeHeight: '34px' },
  { name: 'Creme Bliss', file: '/images/sponsor_creme_bliss.jpeg', maxHeight: '120px', marqueeHeight: '80px' },
  { name: 'Saffron Technologies', file: '/images/sponsor_saffrontechnologies.png', maxHeight: '120px', marqueeHeight: '90px' },
];

// SkyKeen runs the event rather than sponsoring it, so it belongs in the
// marquee but not in the "Side Sponsors" section above. Same 1:1 shape and
// baked-in white background as the other square marks, and the most blank
// canvas of the four — hence the tallest value.
export const MARQUEE_LOGOS = [
  ...SPONSORS,
  { name: 'SkyKeen Events', file: '/images/skykeen2.png', marqueeHeight: '100px' },
];
