// Shared by the Sponsors section and the logo marquee band, so the sponsor
// list only needs to be edited in one place.
//
// These logos have very different intrinsic shapes, so a single size rule
// makes some of them unreadable. Shami Equibooks is a wide 3.5:1 wordmark;
// Creme Bliss and Saffron are 1:1 squares with generous whitespace baked
// into the artwork. Both sizes below are therefore tuned per logo so they
// read at roughly equal optical weight — squares need noticeably more height
// than the wordmark to look the same size.
//
//   maxHeight     — the large Sponsors-section card
//   marqueeHeight — the compact logo chip in the marquee band
export const SPONSORS = [
  { name: 'Shami Equibooks', file: '/images/sponsor_shamiequibooks.png', maxHeight: '54px', marqueeHeight: '36px' },
  { name: 'Creme Bliss', file: '/images/sponsor_creme_bliss.jpeg', maxHeight: '120px', marqueeHeight: '70px' },
  // Saffron's artwork has the most internal whitespace of the three, so it
  // needs the greatest height to match the others optically.
  { name: 'Saffron Technologies', file: '/images/sponsor_saffrontechnologies.png', maxHeight: '120px', marqueeHeight: '78px' },
];
