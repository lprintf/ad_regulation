import { useQuery } from '@tanstack/react-query'
import {
  fetchRuleDefinitions,
  fetchRuleBindings
} from '../../api/ruleEngine'
import type {
  RuleBinding,
  RuleDefinition,
  RuleEntityType
} from '../../types/rule-engine'

export const usePublishedRules = () => {
  const query = useQuery({
    queryKey: ['rule-definitions', 'published'],
    queryFn: () => fetchRuleDefinitions({ status: 'published' }),
    staleTime: 60 * 1000
  })

  const rules: RuleDefinition[] = query.data?.items ?? []
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
