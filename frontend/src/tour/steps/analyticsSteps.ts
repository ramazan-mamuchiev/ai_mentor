import type { DriveStep } from 'driver.js'
import type { TFunction } from 'i18next'

export function getAnalyticsSteps(t: TFunction): DriveStep[] {
  return [
    {
      element: '.analytics-page',
      popover: {
        title: t('help.analytics.overview.title'),
        description: t('help.analytics.overview.desc'),
      },
    },
    {
      element: '.analytics-tabs',
      popover: {
        title: t('help.analytics.tabs.title'),
        description: t('help.analytics.tabs.desc'),
      },
    },
    {
      element: '.stats-grid',
      popover: {
        title: t('help.analytics.stats.title'),
        description: t('help.analytics.stats.desc'),
      },
    },
  ]
}
