import { copyFileSync, mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = dirname(fileURLToPath(import.meta.url))
mkdirSync(join(root, 'dist'), { recursive: true })
for (const name of ['manifest.json', 'popup.html', 'popup.css']) {
  copyFileSync(join(root, name), join(root, 'dist', name))
}
