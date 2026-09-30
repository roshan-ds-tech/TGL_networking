import { go, loginUrl } from './customerApi';

// Modules with a real authenticated page behind them. Awards/Podcasts have no
// product page yet, so they open the public info modal instead.
const AUTHED_ROUTES = {
  vertex: '/app/vertex',
  networking: '/app/networking',
  notifications: '/app/notifications',
  profile: '/app/profile',
};

/* Shared by SiteHeader and Footer. A module with a product page goes straight
   there when signed in, or to sign-in with ?next= so the user lands on the
   page they clicked afterwards. If the session check hasn't settled yet, go
   to the page anyway — ProductApp's guard makes the same decision. */
export function moduleClickHandler({ authUser, authChecked, onOpenModule }) {
  return (key, after) => (e) => {
    e.preventDefault();
    after?.();
    const route = AUTHED_ROUTES[key];
    if (route) go(authUser || !authChecked ? route : loginUrl(route));
    else onOpenModule?.(key);
  };
}
