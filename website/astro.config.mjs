import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://jmassardo.github.io',
  base: '/octowatch',
  integrations: [
    starlight({
      title: 'OctoWatch',
      description: 'GitHub audit log monitoring and security intelligence platform',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/jmassardo/octowatch' },
      ],
      customCss: ['./src/styles/custom.css'],
      sidebar: [
        {
          label: 'Getting Started',
          autogenerate: { directory: 'getting-started' },
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
