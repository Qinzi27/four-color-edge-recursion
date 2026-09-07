// Copy only explicit public web assets. Research/private folders never enter dist.
import { mkdir, readdir, copyFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
const source = new URL('../web/', import.meta.url);
const target = new URL('../dist/', import.meta.url);
await mkdir(target, { recursive:true });
const files = (await readdir(source, {withFileTypes:true})).filter(item => item.isFile());
for (const item of files) await copyFile(new URL(item.name, source), new URL(item.name, target));
// Preserve the existing, self-contained theory explainer as a separate public page.
await copyFile(new URL('../docs/explainer.html', import.meta.url), new URL('model.html', target));
console.log('Built ' + (files.length+1) + ' public assets in ' + fileURLToPath(target));
