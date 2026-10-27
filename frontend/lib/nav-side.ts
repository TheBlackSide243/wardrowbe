import { useEffect, useState } from 'react';

// On a screen wider than it is tall and narrower than the desktop layout (a phone on its side,
// a foldable's wide screen) the bottom tabs stand in a column on the right edge instead, so the
// page keeps its height (globals.css, .mobile-nav).
//
// A right edge this wide is not a camera cutout (an iPhone on its side keeps about 60px there):
// it is a column the system writes the time and the battery in, as the iPhone Duo's closed screen
// does (about 80px, the status block about 150px tall). There the tabs fill that column, below
// the status block (body.nav-status), instead of standing beside it.
export const STATUS_COLUMN_MIN = 70;

export const statusColumn = (rightInset: number) => Number(rightInset) >= STATUS_COLUMN_MIN;

/** The right safe-area inset in px, measured as CSS sees it, kept up to date on resize. */
export function useRightInset() {
  const [inset, setInset] = useState(0);
  useEffect(() => {
    const probe = document.createElement('div');
    probe.style.cssText =
      'position:fixed;visibility:hidden;pointer-events:none;padding-right:env(safe-area-inset-right,0px)';
    document.body.appendChild(probe);
    const measure = () => setInset(parseFloat(getComputedStyle(probe).paddingRight) || 0);
    measure();
    window.addEventListener('resize', measure);
    return () => {
      window.removeEventListener('resize', measure);
      probe.remove();
    };
  }, []);
  return inset;
}
