import { useQuery } from '@tanstack/react-query'
import {
  fetchAvailableRules,
  fetchRuleBindings
} from '../../api/ruleEngine'
import type {
  RuleDefinition,
  RuleEntityType
} from '../../types/rule-engine'

export const usePublishedRules = () => {
  const query = useQuery({
    queryKey: ['available-rules'],
    queryFn: fetchAvailableRules,
    staleTime: 60 * 1000
  })

  const rules: RuleDefinition[] = query.data ?? []
  return {
    ...query,
    rules
  }
}

export const useEntityRuleBindings = (
  entityId: string | null | undefined,
  entityType: RuleEntityType | null | undefined,
  enabled: boolean
) => {
  return useQuery({
    queryKey: ['rule-bindings', { entityId, entityType }],
    queryFn: () =>
      fetchRuleBindings({
        entityId: entityId ?? undefined,
        entityType: entityType ?? undefined,
        activeOnly: false
      }),
    enabled: Boolean(entityId && entityType && enabled),
    staleTime: 30 * 1000
  })
}
