import { type SVGAttributes } from 'react';

// MAFD mark: a fault-signature waveform (a voltage sag / recovery) inside the
// current color. Simple, monoline, reads at 16–24px.
export default function AppLogoIcon(props: SVGAttributes<SVGElement>) {
	return (
		<svg
			{...props}
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth={2}
			strokeLinecap="round"
			strokeLinejoin="round"
			xmlns="http://www.w3.org/2000/svg"
		>
			<path d="M2 12h4l2 6 3-14 3 10 2-4h6" />
		</svg>
	);
}
