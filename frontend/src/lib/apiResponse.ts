/**
 * API响应数据解包工具函数
 * 统一处理后端返回的响应格式，减少重复代码
 */

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyObject = Record<string, any>

/**
 * 从API响应中提取data字段
 * 处理 {data: T} 或直接返回 T 的情况
 */
export const extractResponseData = <T = AnyObject>(response: AnyObject | null | undefined, fallback?: T): T => {
  if (response?.data !== undefined) {
    return response.data as T
  }
  return (response ?? fallback) as T
}

/**
 * 从API响应中提取嵌套的payload数据
 * 处理多层嵌套：data?.data, data?.items, 或直接数组等情况
 */
export const extractResponsePayload = <T = AnyObject>(response: AnyObject | null | undefined, fallback?: T): T => {
  const data = extractResponseData<AnyObject>(response)

  if (Array.isArray(data)) {
    return data as T
  }

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
  response: AnyObject | null | undefined,
  mapFn?: (item: AnyObject) => T
): PaginatedResult<T> => {
  const payload = extractResponseData(response)

  // Handle array response directly
  if (Array.isArray(payload)) {
    const items = mapFn ? payload.map(mapFn) : (payload as unknown as T[])
    return { items, total: items.length, page: 1, pageSize: items.length || 50 }
  }

  // Extract items from object response
  const rawItems: AnyObject[] = (() => {
    if (Array.isArray(payload?.data)) return payload.data
    if (Array.isArray(payload?.items)) return payload.items
    if (Array.isArray(payload?.data?.items)) return payload.data.items
    return []
  })()

  const items = mapFn ? rawItems.map(mapFn) : (rawItems as unknown as T[])
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
export const extractSingleObject = <T = AnyObject>(response: AnyObject | null | undefined, fallback?: T): T => {
  const data = extractResponseData<AnyObject>(response)
  return (data?.data ?? data ?? fallback) as T
}
