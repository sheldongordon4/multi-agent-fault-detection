import { useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { X } from 'lucide-react';
import { useStore } from '../../../app/store';
import { useIsMobile } from '../../../shared/hooks/use-mobile';
import { Button } from '../../../shared/components/ui/button';
import { GridMapCanvas } from '../../map/components/grid-map-canvas';
import {
	IncidentDetail,
	IncidentDetailError,
	IncidentDetailSkeleton,
} from '../components/incident-detail';
import { IncidentListSheet } from '../components/incident-list-sheet';
import {
	OverviewDrawer,
	type DrawerDetent,
} from '../components/overview-drawer';
import { useFetchIncident } from '../hooks/use-fetch-incident';
import { useFetchIncidents } from '../hooks/use-fetch-incidents';
import { filterIncidents } from '../utils/helpers';

// Keeps the fitted island inside the strip of map the panels don't cover.
const LIST_PANEL_WIDTH = 360;
const DETAIL_PANEL_WIDTH = 520;
const EDGE_GUTTER = 24;

export default function Incidents() {
	// The URL owns selection so a ticket is deep-linkable and the back button works.
	const { incidentId } = useParams<{ incidentId: string }>();
	const selectedIncidentId = incidentId ?? null;
	const navigate = useNavigate();

	const search = useStore((state) => state.incidentSearch);
	const severity = useStore((state) => state.incidentSeverity);
	const status = useStore((state) => state.incidentStatus);
	const bus = useStore((state) => state.incidentBus);
	const setIncidentBus = useStore((state) => state.setIncidentBus);

	const [hoveredBusId, setHoveredBusId] = useState<string | null>(null);
	const [listCollapsed, setListCollapsed] = useState(false);
	const [drawerIndex, setDrawerIndex] = useState<DrawerDetent>(0);
	// Reported at rest only, so siblings reflow once per detent rather than per
	// drag frame.
	const [drawerHeight, setDrawerHeight] = useState(0);
	const isMobile = useIsMobile();
	const reducedMotion = useReducedMotion();

	// Clicking a substation filters to it AND opens the sheet — otherwise the
	// results you just asked for would be hidden behind a collapsed panel.
	const handleSelectBus = (busId: string | null) => {
		setIncidentBus(busId);
		if (busId) setListCollapsed(false);
	};

	const {
		incidents,
		isPending: listPending,
		isError: listError,
		refetch: refetchList,
	} = useFetchIncidents();

	const {
		incident,
		isPending: detailPending,
		isError: detailError,
		refetch: refetchDetail,
	} = useFetchIncident(selectedIncidentId);

	const visibleIncidents = useMemo(
		() => filterIncidents(incidents, { search, severity, status, bus }),
		[incidents, search, severity, status, bus]
	);

	const hasFilters =
		search.trim() !== '' || severity !== 'all' || status !== 'all' || !!bus;

	// Which substation the map should ease to: the selected ticket's bus.
	const focusedBusId =
		incident?.bus_id ??
		visibleIncidents.find((i) => i.incident_id === selectedIncidentId)?.bus_id ??
		null;

	const detailOpen = selectedIncidentId !== null;

	// On phones the panels cover the map entirely, and padding wider than the
	// viewport makes fitBounds misbehave — so don't try to dodge them there.
	//
	// Deliberately NOT dependent on `listCollapsed`. The sheet lives in the same
	// left-hand column whether open or shut, so re-fitting on every toggle just
	// made the island lurch up and down for no benefit. Reserving the column
	// permanently keeps the map perfectly still while the sheet slides.
	const mapPadding = useMemo(
		() =>
			isMobile
				? { top: 8, bottom: 32, left: 8, right: 8 }
				: {
						top: EDGE_GUTTER,
						// Clear the drawer as well as the attribution control.
						bottom: EDGE_GUTTER + 24 + drawerHeight,
						left: LIST_PANEL_WIDTH + EDGE_GUTTER,
						right: detailOpen ? DETAIL_PANEL_WIDTH + EDGE_GUTTER : EDGE_GUTTER,
					},
		[detailOpen, isMobile, drawerHeight]
	);

	const closeDetail = () => void navigate('/incidents');

	return (
		<div className="absolute inset-0 overflow-hidden">
			{/* Layer 1 — the map fills the page and sits behind everything. */}
			<div className="absolute inset-0">
				<GridMapCanvas
					incidents={incidents}
					activeBusId={bus}
					focusedBusId={focusedBusId}
					hoveredBusId={hoveredBusId}
					onSelectBus={handleSelectBus}
					padding={mapPadding}
				/>
			</div>

			{/* Layer 2 — the collapsible list sheet, anchored bottom-left. */}
			<div
				className="pointer-events-none absolute inset-y-0 left-0 z-10 flex w-full p-4 md:p-6"
				// The drawer spans the full width, so without this the list's lower
				// edge would sit underneath it.
				style={{
					maxWidth: LIST_PANEL_WIDTH + EDGE_GUTTER,
					paddingBottom: drawerHeight + 16,
				}}
			>
				<IncidentListSheet
					incidents={visibleIncidents}
					selectedIncidentId={selectedIncidentId}
					isPending={listPending}
					isError={listError}
					onRetry={() => void refetchList()}
					hasFilters={hasFilters}
					resultCount={visibleIncidents.length}
					busFilter={bus}
					onClearBusFilter={() => setIncidentBus(null)}
					onHoverIncident={(hovered) =>
						setHoveredBusId(hovered?.bus_id ?? null)
					}
					collapsed={listCollapsed}
					onCollapsedChange={setListCollapsed}
				/>
			</div>

			{/* Layer 3 — the overview drawer: full width, rises over map and list. */}
			{/* No horizontal padding: the drawer runs edge to edge so nothing shows
			    through beside it when it's open. Its own sections carry the inner
			    padding instead. */}
			<div className="pointer-events-none absolute inset-x-0 bottom-0 z-30 h-full">
				<OverviewDrawer
					incidents={incidents}
					isPending={listPending}
					index={drawerIndex}
					onIndexChange={setDrawerIndex}
					onHeightChange={setDrawerHeight}
				/>
			</div>

			{/* Layer 4 — floating detail panel, only while a ticket is selected. */}
			<AnimatePresence>
				{detailOpen && (
					<motion.div
						key="detail"
						// Reduced motion drops the horizontal slide (the vestibular part)
						// but keeps a quick fade, so the panel still reads as arriving
						// rather than teleporting.
						initial={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 24 }}
						animate={{ opacity: 1, x: 0 }}
						exit={reducedMotion ? { opacity: 0 } : { opacity: 0, x: 24 }}
						transition={{ duration: reducedMotion ? 0.12 : 0.18, ease: 'easeOut' }}
						className="pointer-events-none absolute inset-y-0 right-0 z-20 flex w-full p-4 md:p-6"
						style={{ maxWidth: DETAIL_PANEL_WIDTH + EDGE_GUTTER }}
					>
						<FloatingPanel>
							<div className="border-border/60 flex items-center justify-between gap-2 border-b px-3 py-2">
								<span className="truncate text-sm font-semibold">
									Incident detail
								</span>
								<Button
									variant="ghost"
									size="icon"
									className="size-7"
									onClick={closeDetail}
									aria-label="Close incident detail"
								>
									<X className="size-4" />
								</Button>
							</div>

							{/* `@container` so the detail's grids size against THIS panel
							    rather than the viewport — a `sm:` breakpoint would fire off
							    the window width and cram 4 columns into ~470px. */}
							<div className="@container min-h-0 flex-1 overflow-y-auto">
								{detailPending && <IncidentDetailSkeleton />}
								{!detailPending && (detailError || !incident) && (
									<IncidentDetailError onRetry={() => void refetchDetail()} />
								)}
								{!detailPending && !detailError && incident && (
									<IncidentDetail incident={incident} />
								)}
							</div>
						</FloatingPanel>
					</motion.div>
				)}
			</AnimatePresence>
		</div>
	);
}

/**
 * Translucent card that floats over the map. `pointer-events-auto` re-enables
 * interaction inside the panel while its wrapper stays click-through, so the map
 * can still be panned in the gaps around it.
 */
function FloatingPanel({ children }: { children: React.ReactNode }) {
	return (
		<div className="border-border/60 bg-card/85 pointer-events-auto flex min-h-0 w-full flex-col overflow-hidden rounded-xl border shadow-xl backdrop-blur-md">
			{children}
		</div>
	);
}
