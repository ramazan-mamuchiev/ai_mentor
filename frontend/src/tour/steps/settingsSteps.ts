import type { DriveStep } from 'driver.js'
import type { TFunction } from 'i18next'

export function getSettingsSteps(t: TFunction): DriveStep[] {
  return [
    {
      element: '.settings-tabs',
      popover: {
        title: t('help.settings.tabs.title'),
        description: t('help.settings.tabs.desc'),
      },
    },
    {
      element: '.profile-section',
      popover: {
        title: t('help.settings.profile.title'),
        description: t('help.settings.profile.desc'),
      },
    },
    {
      element: '.settings-tab:nth-child(2)',
      popover: {
        title: t('help.settings.apikeys.title'),
        description: t('help.settings.apikeys.desc'),
      },
    },
    {
      element: '.settings-tab:nth-child(3)',
      popover: {
        title: t('help.settings.sharedlinks.title'),
        description: t('help.settings.sharedlinks.desc'),
      },
    },
  ]
}
