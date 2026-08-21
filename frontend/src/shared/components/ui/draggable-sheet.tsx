import {
	useCallback,
	useLayoutEffect,
	useRef,
	useState,
	type ReactNode,
} from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { useElementHeight } from '../../hooks/use-element-height';
import { cn } from '../../lib/utils';

/**
 * A detent height in px, or a function of the space available to the sheet.
 * Callers own the geometry (they know their own content); this component owns
 * the interaction.
 */
export type Detent = number | ((available: number) => number);

// Past this much travel a gesture counts as a drag, not a tap.
const DRAG_SLOP = 6;
// Flick speed (px/ms) that snaps in the flick's direction regardless of distance.
const FLICK_VELOCITY = 0.45;

export interface DraggableSheetProps {
	/** Ascending heights the sheet snaps to. Index 0 is the most closed. */
	detents: Detent[];
	index: number;
	onIndexChange: (index: number) => void;
	/** Reports the live height (including mid-drag) so siblings can make room. */
	onHeightChange?: (height: number) => void;
	/**
	 * Fires when a drag starts and ends. Styling keyed only to `index` is wrong
	 * mid-drag — the index doesn't change until release, so a sheet dragged open
	 * from its closed state keeps its closed appearance while its content is
	 * already visible.
	 */
	onDraggingChange?: (dragging: boolean) => void;
	children: ReactNode;
	className?: string;
	/**
	 * Extra classes for the grabber button. Lets a caller turn the closed state
	 * into a compact floating pill instead of a full-width bar. Merged with
	 * tailwind-merge, so conflicting utilities (w-full, bg-*) override cleanly.
	 */
	grabberClassName?: string;
	/** Describes what activating the grabber does, for screen readers. */
	label?: string;
}

/**
 * Bottom-anchored sheet with a drag grabber and snap detents.
 *
 * Shared by the incident list (2 detents, left column) and the overview drawer
 * (3 detents, full width). The drag handling — pointer capture, tap-vs-drag slop,
 * flick velocity, snapping — is fiddly enough that a second copy would drift, so
 * it lives here once.
 */
export function DraggableSheet({
	detents,
	index,
	onIndexChange,
	onHeightChange,
	onDraggingChange,
	children,
	className,
	grabberClassName,
	label = 'Resize panel',
}: DraggableSheetProps) {
	const [wrapperRef, availableHeight] = useElementHeight<HTMLDivElement>();
	// The grabber is part of the panel, so detents must include it. Measuring it
	// here means callers describe only their own content — otherwise every caller
	// has to remember to add ~26px, and forgetting silently clips the content they
	// asked to keep visible.
	const [grabberRef, grabberHeight] = useElementHeight<HTMLButtonElement>();
	const reducedMotion = useReducedMotion();

	// Non-null only while a drag is in flight, so the sheet tracks the pointer.
	const [dragHeight, setDragHeight] = useState<number | null>(null);
	const gesture = useRef<{
		startY: number;
		startHeight: number;
		lastY: number;
		lastT: number;
		velocity: number;
		moved: boolean;
	} | null>(null);

	const contentAvailable = Math.max(0, availableHeight - grabberHeight);
	const resolved = detents.map((d) => {
		const content = typeof d === 'function' ? d(contentAvailable) : d;
		return grabberHeight + Math.min(Math.max(content, 0), contentAvailable);
	});
	const minHeight = resolved[0] ?? 0;
	const maxHeight = resolved[resolved.length - 1] ?? availableHeight;
	const restingHeight = resolved[index] ?? minHeight;
	const height = dragHeight ?? restingHeight;

	const measured = availableHeight > 0;

	// Report height so siblings (map padding, the other sheet) can make room.
	// Only at rest: firing this per drag frame would push a map setPadding()
	// animation on every pointermove. The sheet overlays them mid-drag anyway, so
	// they only need the final value.
	const lastReported = useRef<number>(-1);
	useLayoutEffect(() => {
		if (!onHeightChange || dragHeight !== null) return;
		if (Math.abs(lastReported.current - restingHeight) < 0.5) return;
		lastReported.current = restingHeight;
		onHeightChange(restingHeight);
	}, [restingHeight, dragHeight, onHeightChange]);

	const nearestIndex = useCallback(
		(h: number) => {
			let best = 0;
			let bestDelta = Infinity;
			resolved.forEach((value, i) => {
				const delta = Math.abs(value - h);
				if (delta < bestDelta) {
					bestDelta = delta;
					best = i;
				}
			});
			return best;
		},
		[resolved]
	);

	const onPointerDown = useCallback(
		(event: React.PointerEvent<HTMLButtonElement>) => {
			if (event.button !== 0) return;
			event.currentTarget.setPointerCapture(event.pointerId);
			gesture.current = {
				startY: event.clientY,
				startHeight: restingHeight,
				lastY: event.clientY,
				lastT: event.timeStamp,
				velocity: 0,
				moved: false,
			};
		},
		[restingHeight]
	);

	const onPointerMove = useCallback(
		(event: React.PointerEvent<HTMLButtonElement>) => {
			const g = gesture.current;
			if (!g) return;

			const dy = event.clientY - g.startY;
			if (!g.moved && Math.abs(dy) > DRAG_SLOP) g.moved = true;
			if (!g.moved) return;

			const dt = event.timeStamp - g.lastT;
			if (dt > 0) {
				// Negative = moving up. Signed so flick direction is readable.
				g.velocity = (event.clientY - g.lastY) / dt;
				g.lastY = event.clientY;
				g.lastT = event.timeStamp;
			}

			// Bottom-anchored: dragging up (negative dy) grows the sheet.
			setDragHeight(Math.min(Math.max(g.startHeight - dy, minHeight), maxHeight));
		},
		[maxHeight, minHeight]
	);

	const endGesture = useCallback(
		(event: React.PointerEvent<HTMLButtonElement>) => {
			const g = gesture.current;
			gesture.current = null;
			if (!g) return;

			if (event.currentTarget.hasPointerCapture(event.pointerId)) {
				event.currentTarget.releasePointerCapture(event.pointerId);
			}

			// A tap (no meaningful travel) is handled by onClick instead.
			if (!g.moved) {
				setDragHeight(null);
				return;
			}

			const current = dragHeight ?? g.startHeight;
			let next = nearestIndex(current);

			// A deliberate flick beats raw position — matching the gesture's
			// direction is what makes this feel responsive rather than sticky.
			if (Math.abs(g.velocity) > FLICK_VELOCITY) {
				const startIndex = nearestIndex(g.startHeight);
				next =
					g.velocity > 0
						? Math.max(0, Math.min(next, startIndex - 1)) // downward → smaller
						: Math.min(resolved.length - 1, Math.max(next, startIndex + 1));
			}

			setDragHeight(null);
			onIndexChange(next);
		},
		[dragHeight, nearestIndex, onIndexChange, resolved.length]
	);

	const dragging = dragHeight !== null;

	useLayoutEffect(() => {
		onDraggingChange?.(dragging);
	}, [dragging, onDraggingChange]);

	return (
		// Absolute is load-bearing, not cosmetic: as a normal flow child the sheet's
		// height would feed back into the wrapper we measure to compute that very
		// height, and it would inflate past the screen.
		<div ref={wrapperRef} className="relative h-full w-full">
			<motion.div
				className={cn(
					'border-border/60 bg-card/85 pointer-events-auto absolute inset-x-0 bottom-0 flex flex-col overflow-hidden rounded-xl border shadow-xl backdrop-blur-md',
					className
				)}
				// The height must ALWAYS be defined: handing it between `style` and
				// `animate` left a frame with neither, and a bottom-anchored element
				// with auto height grows straight off the top of the screen.
				initial={false}
				animate={{ height: measured ? height : '100%' }}
				transition={
					dragging
						? { duration: 0 } // track the pointer exactly
						: reducedMotion
							? // Reduced motion means avoiding vestibular triggers — the
								// springy overshoot — not removing feedback entirely. A short
								// linear move still shows what happened.
								{ duration: 0.12, ease: 'easeOut' }
							: { type: 'spring', stiffness: 420, damping: 38 }
				}
			>
				<button
					ref={grabberRef}
					type="button"
					aria-label={label}
					onPointerDown={onPointerDown}
					onPointerMove={onPointerMove}
					onPointerUp={endGesture}
					onPointerCancel={endGesture}
					onClick={() => {
						// Cycle to the next detent, wrapping. With two detents that's a
						// plain toggle; with three it's a predictable keyboard path.
						if (dragHeight === null) {
							onIndexChange((index + 1) % resolved.length);
						}
					}}
					className={cn(
						'group flex w-full shrink-0 cursor-grab touch-none justify-center py-2.5 active:cursor-grabbing',
						grabberClassName
					)}
				>
					<span className="bg-muted-foreground/40 group-hover:bg-muted-foreground/70 h-1.5 w-10 rounded-full transition-colors" />
				</button>

				{children}
			</motion.div>
		</div>
	);
}
