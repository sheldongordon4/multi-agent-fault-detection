import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useStore } from '@app/store';
import { addComment } from '../services/assignment-service';
import { assignmentQueryKeys } from '../utils/query-keys';

/**
 * Post a comment onto a ticket's activity feed.
 *
 * Not optimistic: a comment is the operator's own words and showing it before
 * the server has it risks the text vanishing on a failure. The feed is short and
 * the refetch is one small request.
 */
export const useAddComment = (incidentId: string) => {
	const queryClient = useQueryClient();
	const actorId = useStore((state) => state.actingOperatorId);

	return useMutation({
		mutationFn: (body: string) => addComment({ incidentId, body, actorId }),
		onSuccess: () => {
			void queryClient.invalidateQueries({
				queryKey: assignmentQueryKeys.events(incidentId),
			});
		},
		onError: () =>
			toast.error("Couldn't post that comment", {
				description: 'The API is unreachable. Your text is still in the box.',
			}),
	});
};
