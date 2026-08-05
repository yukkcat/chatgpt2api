import type { ActionMenuItem } from 'nanocat-ui'

export type ActionMenuGroup<T extends ActionMenuItem = ActionMenuItem> = T[]

export function actionMenuGroups<T extends ActionMenuItem = ActionMenuItem>(...groups: ActionMenuGroup<T>[]): T[] {
  return groups
    .filter((group) => group.length > 0)
    .flatMap((group, groupIndex) => (
      group.map((item, itemIndex) => ({
        ...item,
        dividerBefore: Boolean(item.dividerBefore || (groupIndex > 0 && itemIndex === 0)),
      }))
    ))
}
