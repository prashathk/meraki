import {readFileSync} from 'node:fs';

export function demoPassword() {
  let value = process.env.DEMO_PASSWORD;
  if (value === undefined) {
    let contents = '';
    try { contents = readFileSync(new URL('../.env', import.meta.url), 'utf8'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
    value = contents.match(/^\s*(?:export\s+)?DEMO_PASSWORD\s*=\s*(.*?)\s*$/m)?.[1];
    if (value?.startsWith("'") && value.endsWith("'")) value = value.slice(1, -1).replace(/\\'/g, "'");
    else if (value?.startsWith('"') && value.endsWith('"')) value = JSON.parse(value);
    else value = value?.replace(/\s+#.*$/, '').trim();
  }
  if (!value || value.length < 12) throw new Error('Set a private DEMO_PASSWORD in the root .env, or run python -m scripts.configure_local.');
  return value;
}
