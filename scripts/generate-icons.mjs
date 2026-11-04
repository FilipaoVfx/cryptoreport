import { chromium } from 'playwright';
import { readFile, writeFile } from 'node:fs/promises';
const folder = new URL('../web/icons/', import.meta.url);
const svg = await readFile(new URL('source.svg', folder), 'utf8');
const browser = await chromium.launch({ args: ['--no-sandbox'], ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH } : {}) });
try {
  for (const [name, size] of [['icon-192', 192], ['icon-512', 512], ['maskable-512', 512], ['apple-touch-icon', 180]]) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await page.setContent('<style>html,body{margin:0;width:100%;height:100%;background:#0b0717}svg{display:block;width:100%;height:100%}</style>' + svg);
    await writeFile(new URL(name + '.png', folder), await page.screenshot());
    await page.close();
  }
} finally { await browser.close(); }
