export default function LoadingPage({
	message = 'Loading…',
}: {
	message?: string;
}) {
	return (
		<div className="bg-background flex h-screen flex-col items-center justify-center gap-4">
			<div className="border-muted border-t-primary size-10 animate-spin rounded-full border-4" />
			<p className="text-muted-foreground text-sm">{message}</p>
		</div>
	);
}
