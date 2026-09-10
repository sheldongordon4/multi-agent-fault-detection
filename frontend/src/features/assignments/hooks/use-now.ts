import { useEffect, useState } from 'react';

/**
 * A clock that re-renders on an interval.
 *
 * Age and SLA are derived from `Date.now()` at render time, and nothing else on
 * an idle board triggers a render — so without this a ticket that went overdue
 * ten minutes ago still reads "25m left" on a control-room screen left open.
 * The column whose whole job is to say time ran out has to keep saying it.
 *
 * 30s is well under the tightest thing displayed (minutes) and costs one
 * re-render of a table that is already cheap.
 */
export function useNow(intervalMs = 30_000): number {
	const [now, setNow] = useState(() => Date.now());

	useEffect(() => {
		const id = setInterval(() => setNow(Date.now()), intervalMs);
		return () => clearInterval(id);
	}, [intervalMs]);

	return now;
}
