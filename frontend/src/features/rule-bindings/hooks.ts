import { useQuery } from '@tanstack/react-query'
import {
  fetchAvailableRules,
  fetchRuleBindings,
  fetchRuleConfigs
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

/**
 * 获取所有可用规则：系统规则 + 用户配置的规则
 * 用于托管弹窗的规则选择
 */
export interface CombinedRule {
  id: string          // 规则名或config id
  name: string        // 显示名称
  description: string
  version: string
  isUserConfig: boolean  // 是否是用户配置
  configId?: string      // 如果是用户配置，存储 config id
  baseRule?: string      // 如果是用户配置，存储基础规则名
}

export const useAllRulesForBinding = () => {
  const availableRulesQuery = useQuery({
    queryKey: ['available-rules'],
    queryFn: fetchAvailableRules,
    staleTime: 60 * 1000
  })

  const configsQuery = useQuery({
    queryKey: ['rule-configs-for-binding'],
    queryFn: () => fetchRuleConfigs({ includeArchived: false }),
    staleTime: 30 * 1000
  })

  const combinedRules: CombinedRule[] = []

  // 添加系统规则（从 available rules）
  const availableRules = availableRulesQuery.data ?? []
  for (const rule of availableRules) {
    combinedRules.push({
      id: rule.name,
      name: rule.name,
      description: rule.description || '',
      version: rule.version,
      isUserConfig: false
    })
  }

  // 添加用户配置的规则（非系统来源）
  const configs = configsQuery.data ?? []
  for (const config of configs) {
    // 跳过系统规则（已经从 available rules 添加）
    if (config.source === 'system') continue

    combinedRules.push({
      id: config.name,  // 使用 config name 作为绑定时的 rule_id
      name: config.name,
      description: config.description ?? `基于 ${config.base_rule}`,
      version: config.version,
      isUserConfig: true,
      configId: config.id,
      baseRule: config.base_rule
    })
  }

  return {
    rules: combinedRules,
    isLoading: availableRulesQuery.isLoading || configsQuery.isLoading,
    isError: availableRulesQuery.isError || configsQuery.isError
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
