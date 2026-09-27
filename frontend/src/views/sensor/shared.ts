/** 观测传感器模块共享口径：动作可用性、检定有效期缺失判定，列表页与详情页共用。 */

export type SensorStatus = '待检定' | '正常采集' | '疑误待查' | '已拆除'

export const ENDPOINT = '/api/sensor'

export const COLUMNS = [
  '传感器编号',
  '所属站点',
  '观测要素',
  '设备型号',
  '出厂序列号',
  '安装高度',
  '检定有效期',
  '传感器状态',
] as const

export const DETAIL_FIELDS = COLUMNS

export const ACTIONS = ['安排检定', '标记疑误', '拆除传感器'] as const
export type SensorAction = (typeof ACTIONS)[number]

/** 与后端状态机一致：只有当前状态在 from 集合里，动作才可用。已拆除是终态。 */
export const ACTION_FROM: Record<SensorAction, SensorStatus[]> = {
  安排检定: ['待检定', '疑误待查'],
  标记疑误: ['正常采集'],
  拆除传感器: ['待检定', '正常采集', '疑误待查'],
}

export function actionEnabled(action: SensorAction, status: string | null | undefined): boolean {
  return ACTION_FROM[action].includes((status ?? '') as SensorStatus)
}

/** 检定有效期缺失：空串、占位文本或无法解析的日期都算，便于一眼定位。 */
export function validityMissing(raw: unknown): boolean {
  const text = String(raw ?? '').trim()
  if (!text || text.startsWith('观测传感器样例')) {
    return true
  }
  const value = new Date(text.slice(0, 10))
  return Number.isNaN(value.getTime())
}
