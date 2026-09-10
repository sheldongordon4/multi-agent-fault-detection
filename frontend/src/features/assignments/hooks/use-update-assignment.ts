import { useMutation, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { toast } from 'sonner';
import { useStore } from '@app/store';
import type {
	Assignment,
	AssignmentListResponse,
	AssignmentUpdate,
} from '@shared/types';
import { updateAssignment } from '../services/assignment-service';
import type { AssignmentFilters } from '../store/assignment-slice';
import { assignmentQueryKeys } from '../utils/query-keys';

type Variables = {
	incidentId: string;
	patch: AssignmentUpdate;
	/** Optimistic display values the patch implies but doesn't itself carry. */
	optimistic?: Partial<Assignment>;
};

/**
 * Assign / unassign / change state, applied optimistically.
 *
 * Two failure modes are handled differently. A 409 means someone else moved the
 * ticket first — the local edit is rolled back and the row refetched, because
 * retrying would overwrite their change. Anything else is a plain failure and
 * just rolls back.
 *
 * `filters` is optional: callers rendering a list pass theirs so the row updates
 * instantly, while the detail panel — which the map page opens with no list in
 * sight — omits them and relies on the invalidation in `onSettled`.
 */
export const useUpdateAssignment = (filters?: AssignmentFilters) => {
	const queryClient = useQueryClient();
	const actorId = useStore((state) => state.actingOperatorId);

	const listKey = filters ? assignmentQueryKeys.list(filters) : null;

	return useMutation({
		mutationFn: ({ incidentId, patch }: Variables) =>
			updateAssignment({ incidentId, patch, actorId }),

		onMutate: async ({ incidentId, patch, optimistic }: Variables) => {
			if (!listKey) return { previous: undefined };

			// Stop an in-flight refetch from landing on top of the optimistic edit.
			await queryClient.cancelQueries({ queryKey: listKey });
			const previous = queryClient.getQueryData<AssignmentListResponse>(listKey);

			queryClient.setQueryData<AssignmentListResponse>(listKey, (current) => {
				if (!current) return current;
				return {
					...current,
					items: current.items.map((item) =>
						item.incident_id === incidentId
							? { ...item, ...patch, ...optimistic }
							: item
					),
				};
			});

			return { previous };
		},

		// The response carries the new `version`. Without writing it back, the
		// cached row keeps the pre-write version until the refetch lands, and a
		// second click in that window sends a stale `expected_version` — earning
		// the user a 409 that blames a colleague for their own previous change.
		onSuccess: (updated) => {
			// The detail query is keyed by id, so it is refreshed either way.
			queryClient.setQueryData(
				assignmentQueryKeys.detail(updated.incident_id),
				updated
			);

			if (!listKey) return;

			queryClient.setQueryData<AssignmentListResponse>(listKey, (current) => {
				if (!current) return current;
				return {
					...current,
					items: current.items.map((item) =>
						item.incident_id === updated.incident_id ? updated : item
					),
				};
			});
		},

		onError: (error, _variables, context) => {
			if (listKey && context?.previous) {
				queryClient.setQueryData(listKey, context.previous);
			}

			const conflict =
				axios.isAxiosError(error) && error.response?.status === 409;

			if (conflict) {
				toast.error('Someone else updated this ticket', {
					description:
						'Your change was not applied. The ticket has been reloaded.',
				});
			} else {
				toast.error("Couldn't update the ticket", {
					description: 'The API is unreachable or rejected the change.',
				});
			}
		},

		onSettled: (_data, _error, { incidentId }) => {
			void queryClient.invalidateQueries({ queryKey: assignmentQueryKeys.all });
			void queryClient.invalidateQueries({
				queryKey: assignmentQueryKeys.events(incidentId),
			});
			// The roster carries per-operator open counts, which any state or
			// assignee change can move.
			void queryClient.invalidateQueries({ queryKey: ['operators'] });
		},
	});
};
