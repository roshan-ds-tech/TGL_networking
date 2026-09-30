import { go } from '../../lib/customerApi';

const TABS = [
  ['Overview', '/app/networking'],
  ['Members', '/app/networking/members'],
  ['Referrals', '/app/networking/referrals'],
  ['Need Board', '/app/networking/needs'],
];

export default function NetTabs({ active }) {
  return (
    <div style={{ borderBottom: '1px solid rgba(53,26,78,0.1)', background: 'rgba(255,252,245,0.5)' }}>
      <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px', display: 'flex', gap: 30, overflowX: 'auto' }}>
        {TABS.map(([label, target]) => {
          const on = active === label;
          return (
            <button
              key={label}
              type="button"
              onClick={() => go(target)}
              style={{ padding: '18px 0 16px', border: 'none', borderBottom: `2px solid ${on ? '#C08D2E' : 'transparent'}`, background: 'none', fontSize: 11.5, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', color: on ? '#2B1740' : 'rgba(43,23,64,0.55)' }}
            >
              {label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
