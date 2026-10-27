'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, Shirt, Sparkles, LayoutGrid, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { navOnSide, statusColumn, useRightInset, useWideScreen } from '@/lib/nav-side';
import { useTranslations } from 'next-intl';

export function MobileNav() {
  const pathname = usePathname();
  const t = useTranslations('nav');
  const wide = useWideScreen();
  const rightInset = useRightInset();
  const onSide = navOnSide(wide, rightInset);
  const inStatusColumn = statusColumn(rightInset);

  // Classes on the body, so the page and the upload queue make room for the column (globals.css).
  useEffect(() => {
    document.body.classList.toggle('nav-side', onSide);
    document.body.classList.toggle('nav-status', inStatusColumn);
    return () => document.body.classList.remove('nav-side', 'nav-status');
  }, [onSide, inStatusColumn]);

  const navigation = [
    { name: t('dashboard'), href: '/dashboard', icon: Home },
    { name: t('wardrobe'), href: '/dashboard/wardrobe', icon: Shirt },
    { name: t('suggest'), href: '/dashboard/suggest', icon: Sparkles },
    { name: t('outfits'), href: '/dashboard/outfits', icon: LayoutGrid },
    { name: t('settings'), href: '/dashboard/settings', icon: Settings },
  ];

  return (
    <nav className="mobile-nav fixed bottom-0 left-0 right-0 z-50 border-t bg-background pb-[var(--sab)] lg:hidden">
      <div className="mobile-nav-tabs flex h-16 items-center justify-around">
        {navigation.map((item) => {
          const isActive = item.href === '/dashboard'
            ? pathname === '/dashboard'
            : pathname === item.href || pathname.startsWith(item.href + '/');
          return (
            <Link
              key={item.name}
              href={item.href}
              className={cn(
                'flex flex-col items-center gap-1 px-3 py-2 text-xs',
                isActive
                  ? 'text-primary'
                  : 'text-muted-foreground hover:text-foreground'
              )}
            >
              <item.icon className="h-5 w-5" aria-hidden="true" />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
