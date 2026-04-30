import { visit } from 'unist-util-visit';

/**
 * Rehype plugin that transforms ```mermaid code blocks into
 * <pre class="mermaid"> elements for client-side rendering.
 */
export function rehypeMermaid() {
  return (tree) => {
    visit(tree, 'element', (node, index, parent) => {
      if (
        node.tagName === 'pre' &&
        node.children?.[0]?.tagName === 'code' &&
        node.children[0].properties?.className?.includes('language-mermaid')
      ) {
        const code = node.children[0];
        const value = code.children
          ?.map((child) => (child.type === 'text' ? child.value : ''))
          .join('');

        parent.children[index] = {
          type: 'element',
          tagName: 'pre',
          properties: { className: ['mermaid'] },
          children: [{ type: 'text', value }],
        };
      }
    });
  };
}
