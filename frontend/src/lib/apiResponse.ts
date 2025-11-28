/**
 * API响应数据解包工具函数
 * 统一处理后端返回的响应格式，减少重复代码
 */

/**
 * 从API响应中提取data字段
 * 处理 {data: T} 或直接返回 T 的情况
 */
export const extractResponseData = <T>(response: any, fallback?: T): T => {
  if (response?.data !== undefined) {
    return response.data as T
  }
  return (response ?? fallback) as T
}

/**
 * 从API响应中提取嵌套的payload数据
 * 处理多层嵌套：data?.data, data?.items, 或直接数组等情况
 */
export const extractResponsePayload = <T>(response: any, fallback?: T): T => {
  const data = extractResponseData(response)

  // 如果data本身是数组，直接返回
  if (Array.isArray(data)) {
    return data as T
  }

  // 尝试从多个可能的字段中提取数据
  return (data?.items ?? data?.data ?? data ?? fallback) as T
}

/**
 * 从API响应中提取分页列表数据
 * 返回统一的分页响应格式
 */
export interface PaginatedResult<T> {
  items: T[]
  total: number
  page: number
  pageSize: number
}

export const extractPaginatedResponse = <T>(
  response: any,
  mapFn?: (item: any) => T
): PaginatedResult<T> => {
  const payload = extractResponseData(response)

  // 提取原始items数组
  const rawItems: any[] = (() => {
    if (Array.isArray(payload?.data)) {
      return payload.data
    }
    if (Array.isArray(payload)) {
      return payload
    }
    if (Array.isArray(payload?.items)) {
      return payload.items
    }
    if (Array.isArray(payload?.data?.items)) {
      return payload.data.items
    }
    return []
  })()

  // 应用映射函数（如果提供）
  const items = mapFn ? rawItems.map(mapFn) : rawItems

  // 提取total
  const total = payload?.data?.total ?? payload?.total ?? rawItems.length

  return {
    items,
    total: typeof total === 'number' ? total : 0,
    page: payload?.data?.page ?? payload?.page ?? 1,
    pageSize: payload?.data?.pageSize ?? payload?.pageSize ?? (items.length || 50)
  }
}

/**
 * 从API响应中提取单个对象
 * 处理 {data: {data: T}} 或 {data: T} 的情况
 */
export const extractSingleObject = <T>(response: any, fallback?: T): T => {
  const data = extractResponseData(response)
  return (data?.data ?? data ?? fallback) as T
}
