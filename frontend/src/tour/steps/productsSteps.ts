import type { DriveStep } from 'driver.js'
import type { TFunction } from 'i18next'

export function getProductsSteps(t: TFunction): DriveStep[] {
  return [
    {
      element: '.docs-page-title',
      popover: {
        title: t('help.products.overview.title'),
        description: t('help.products.overview.desc'),
      },
    },
    {
      element: '.docs-toolbar',
      popover: {
        title: t('help.products.toolbar.title'),
        description: t('help.products.toolbar.desc'),
      },
    },
    {
      element: '.docs-table-wrap',
      popover: {
        title: t('help.products.table.title'),
        description: t('help.products.table.desc'),
      },
    },
  ]
}
