import type { DriveStep } from 'driver.js'
import type { TFunction } from 'i18next'

export function getChatSteps(t: TFunction): DriveStep[] {
  return [
    {
      element: '.sidebar-nav',
      popover: {
        title: t('help.chat.nav.title'),
        description: t('help.chat.nav.desc'),
      },
    },
    {
      element: '.chat-input-wrapper',
      popover: {
        title: t('help.chat.input.title'),
        description: t('help.chat.input.desc'),
      },
    },
    {
      element: '.chat-product-header',
      popover: {
        title: t('help.chat.product.title'),
        description: t('help.chat.product.desc'),
      },
    },
    {
      element: '.empty-suggestions',
      popover: {
        title: t('help.chat.suggestions.title'),
        description: t('help.chat.suggestions.desc'),
      },
    },
  ]
}
