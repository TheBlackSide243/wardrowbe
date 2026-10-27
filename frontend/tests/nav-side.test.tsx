import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { MobileNav } from '@/components/mobile-nav';
import { STATUS_COLUMN_MIN, navOnSide, statusColumn } from '@/lib/nav-side';

vi.mock('next/navigation', () => ({ usePathname: () => '/dashboard' }));
vi.mock('next-intl', () => ({ useTranslations: () => (key: string) => key }));

describe('tabs on the right', () => {
  it('takes a wide right edge for the status column, not a camera cutout', () => {
    expect(statusColumn(0)).toBe(false);
    // An iPhone on its side keeps about 60px for the camera.
    expect(statusColumn(59)).toBe(false);
    expect(statusColumn(STATUS_COLUMN_MIN)).toBe(true);
    // The iPhone Duo closed, about 81px measured.
    expect(statusColumn(81)).toBe(true);
  });

  it('puts the tabs on the right on a wide screen, or in a status column whichever way it turns', () => {
    expect(navOnSide(false, 0)).toBe(false);
    expect(navOnSide(true, 0)).toBe(true);
    // The Duo closed is taller than it is wide: the status column alone puts the tabs there.
    expect(navOnSide(false, 81)).toBe(true);
    expect(navOnSide(false, 47)).toBe(false);
  });

  it('marks the body only while the right edge is a status column', () => {
    const { unmount } = render(<MobileNav />);
    // jsdom has no safe areas: the inset reads 0.
    expect(document.body.classList.contains('nav-status')).toBe(false);
    expect(document.body.classList.contains('nav-side')).toBe(false);
    unmount();
    expect(document.body.classList.contains('nav-status')).toBe(false);
  });

  it('keeps the side column in CSS, below the desktop layout', () => {
    const css = readFileSync(resolve(__dirname, '../app/globals.css'), 'utf8');
    expect(css).toContain('@media (max-width: 1023px)');
    expect(css).toContain('body.nav-side.nav-status .mobile-nav');
    expect(css).toContain('--sar: env(safe-area-inset-right, 0px)');
  });
});
