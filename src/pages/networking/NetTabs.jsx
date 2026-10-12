import { go } from '../../lib/customerApi';
import { useConnections } from '../../lib/connections';

const TABS = [
  ['Overview', '/app/networking'],
  ['Members', '/app/networking/members'],
  ['My Network', '/app/networking/connections'],
  ['Referrals', '/app/networking/referrals'],
  ['Need Board', '/app/networking/needs'],
];

export default function NetTabs({ active }) {
  // Invitations waiting on you, so a request never sits unseen.
  const { invitations } = useConnections();
  const waiting = invitations.length;
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
              aria-current={on ? 'page' : undefined}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '18px 0 16px', border: 'none', borderBottom: `2px solid ${on ? '#C08D2E' : 'transparent'}`, background: 'none', fontSize: 11.5, fontWeight: 700, letterSpacing: '.16em', textTransform: 'uppercase', cursor: 'pointer', whiteSpace: 'nowrap', color: on ? '#2B1740' : 'rgba(43,23,64,0.55)' }}
            >
              {label}
              {label === 'My Network' && waiting > 0 && (
                <span aria-label={`${waiting} invitation${waiting === 1 ? '' : 's'} waiting`} style={{ minWidth: 18, height: 18, padding: '0 5px', display: 'inline-grid', placeItems: 'center', borderRadius: 999, background: '#C08D2E', color: '#22103A', fontSize: 10.5, letterSpacing: 0 }}>{waiting}</span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
