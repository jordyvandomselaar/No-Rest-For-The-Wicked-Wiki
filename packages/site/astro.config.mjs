// @ts-check
import { defineConfig } from 'astro/config';

import react from '@astrojs/react';
import sitemap from '@astrojs/sitemap';
import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  site: process.env.SITE_URL ?? 'https://nrftw.jordy.app/',
  integrations: [react(), sitemap()],

  vite: {
    plugins: [tailwindcss()]
  }
});
