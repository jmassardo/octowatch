/**
 * Factory function that creates a React component for a specific custom query
 * widget instance. This is a .ts file (not .tsx) to avoid the
 * react-refresh/only-export-components rule.
 */

import { createElement, type ComponentType } from 'react';
import { CustomQueryWidgetInstance } from './CustomQueryWidgetInstance';

/**
 * Creates a React component for a specific custom widget instance.
 * Returns a zero-prop component that renders the widget for the given ID.
 */
export function createCustomQueryWidgetComponent(widgetId: string): ComponentType {
  function CustomQueryWidgetWrapper() {
    return createElement(CustomQueryWidgetInstance, { widgetId });
  }

  CustomQueryWidgetWrapper.displayName = `CustomQueryWidget(${widgetId})`;
  return CustomQueryWidgetWrapper;
}
