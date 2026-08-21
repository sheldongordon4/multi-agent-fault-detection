import { useEffect, useState } from 'react';
import { useStore } from '@app/store';

const DARK_QUERY = '(prefers-color-scheme: dark)';

/**
 * The concrete theme currently on screen.
 *
 * The store keeps the user's *preference* ('light' | 'dark' | 'system'); anything
 * that has to pick real colours — the map basemap, for instance — needs 'system'
 * resolved to what the OS actually reports, and needs to follow the OS if that
 * changes while the preference stays on 'system'.
 */
export function useResolvedTheme(): 'light' | 'dark' {
	const theme = useStore((state) => state.theme);
	const [systemDark, setSystemDark] = useState(
		() => window.matchMedia(DARK_QUERY).matches
	);

	useEffect(() => {
		if (theme !== 'system') return;
		const media = window.matchMedia(DARK_QUERY);
		const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
		media.addEventListener('change', onChange);
		// Re-sync on subscribe in case the OS changed while we weren't listening.
		setSystemDark(media.matches);
		return () => media.removeEventListener('change', onChange);
	}, [theme]);

	if (theme === 'system') return systemDark ? 'dark' : 'light';
	return theme;
}
