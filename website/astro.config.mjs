import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import { rehypeMermaid } from './src/plugins/rehype-mermaid.mjs';

export default defineConfig({
  site: 'https://jmassardo.github.io',
  base: '/octowatch',
  markdown: {
    rehypePlugins: [rehypeMermaid],
  },
  integrations: [
    starlight({
      title: 'OctoWatch',
      description: 'GitHub audit log monitoring and security intelligence platform',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/jmassardo/octowatch' },
      ],
      customCss: ['./src/styles/custom.css'],
      head: [
        {
          tag: 'script',
          attrs: { type: 'module' },
          content: `
            import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
            mermaid.initialize({
              startOnLoad: true,
              theme: 'dark',
              themeVariables: {
                primaryColor: '#1e293b',
                primaryTextColor: '#e2e8f0',
                primaryBorderColor: '#3b82f6',
                lineColor: '#94a3b8',
                secondaryColor: '#1a2744',
                tertiaryColor: '#0f172a',
              },
            });
          `,
        },
      ],
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'Introduction', slug: 'getting-started/introduction' },
            { label: 'Prerequisites', slug: 'getting-started/prerequisites' },
            { label: 'Installation', slug: 'getting-started/installation' },
            { label: 'First Login', slug: 'getting-started/first-login' },
          ],
        },
        {
          label: 'Guides',
          autogenerate: { directory: 'guides' },
        },
        {
          label: 'Reference',
          autogenerate: { directory: 'reference' },
        },
      ],
    }),
  ],
});
