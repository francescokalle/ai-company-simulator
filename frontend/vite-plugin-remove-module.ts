/**
 * Vite plugin to remove type="module" and crossorigin from script tags
 * This allows the IIFE bundle to work as a classic script
 */
export function removeModuleScriptAttrs() {
  return {
    name: 'remove-module-script-attrs',
    transformIndexHtml(html) {
      return html
        .replace(/<script type="module" crossorigin src="([^"]+)"><\/script>/, '<script src="$1"></script>')
        .replace(/<script type="module" src="([^"]+)"><\/script>/, '<script src="$1"></script>');
    },
  };
}
