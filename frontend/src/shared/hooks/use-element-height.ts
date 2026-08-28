import { useLayoutEffect, useRef, useState } from 'react';

/**
 * Live height of an element, via ResizeObserver.
 *
 * Hand-rolled rather than pulling in a measuring library: this value drives an
 * animated height, so a silent 0 either collapses a sheet to nothing or stops it
 * animating at all. Small enough to own, and we hit exactly that failure with a
 * library before.
 *
 * Lives in its own module rather than beside <DraggableSheet>: React Fast Refresh
 * only handles a module whose exports are all components, so shipping this hook
 * from the same file forced a full page reload on every edit to it.
 */
export function useElementHeight<T extends HTMLElement>() {
	const ref = useRef<T | null>(null);
	const [height, setHeight] = useState(0);

	// Layout effect, not effect: this drives what gets painted, so measuring after
	// paint flashes a wrongly-sized element on every mount.
	useLayoutEffect(() => {
		const element = ref.current;
		if (!element) return;

		const apply = (next: number) =>
			setHeight((prev) => (Math.abs(prev - next) > 0.5 ? next : prev));

		const observer = new ResizeObserver(([entry]) => {
			apply(entry.borderBoxSize?.[0]?.blockSize ?? entry.contentRect.height);
		});
		observer.observe(element);

		apply(element.getBoundingClientRect().height);

		// Re-measure on the next macrotask. The synchronous read above can land
		// before layout settles and return 0, and ResizeObserver only delivers
		// during the rendering steps — which a backgrounded tab skips entirely, so
		// it would never correct itself. A timeout fires either way.
		const timer = window.setTimeout(() => {
			if (ref.current) apply(ref.current.getBoundingClientRect().height);
		}, 0);

		return () => {
			window.clearTimeout(timer);
			observer.disconnect();
		};
	}, []);

	return [ref, height] as const;
}
