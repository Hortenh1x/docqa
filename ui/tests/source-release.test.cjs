const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, mkdirSync, writeFileSync, rmSync, symlinkSync } = require('node:fs');
const { tmpdir } = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const { spawnSync } = require('node:child_process');

const script = path.resolve(__dirname, '../scripts/verify-source.mjs');
const hash = data => createHash('sha256').update(data).digest('hex');
function fixture(t) {
  const root = mkdtempSync(path.join(tmpdir(), 'docqa-source-ui-'));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  mkdirSync(path.join(root, 'src'), { recursive: true });
  mkdirSync(path.join(root, 'public/source'), { recursive: true });
  const archive = `docqa-source-${'a'.repeat(64)}.tar.gz`;
  writeFileSync(path.join(root, 'src/page.tsx'), 'original');
  writeFileSync(path.join(root, 'public/source', archive), 'archive bytes');
  writeFileSync(path.join(root, 'public/source/LICENSE.txt'), 'license');
  writeFileSync(path.join(root, 'public/source/manifest.json'), JSON.stringify({
    format: 1, archive, sha256: hash('archive bytes'),
    files: { 'ui/src/page.tsx': { sha256: hash('original') }, LICENSE: { sha256: hash('license') } },
  }));
  return { root, archive, run: (...args) => spawnSync(process.execPath, [script, ...args], { cwd: root, encoding: 'utf8' }) };
}

test('accepts a matching prepared UI and archive', t => {
  const { run } = fixture(t);
  const result = run();
  assert.equal(result.status, 0, result.stderr);
});

test('rejects source edited after packaging', t => {
  const { root, run } = fixture(t);
  writeFileSync(path.join(root, 'src/page.tsx'), 'modified');
  const result = run();
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Source changed after packaging/);
});

test('rejects a corrupt download', t => {
  const { root, archive, run } = fixture(t);
  writeFileSync(path.join(root, 'public/source', archive), 'corrupt');
  const result = run();
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Archive checksum/);
});

test('requires a release for Docker but permits an unpackaged local build', t => {
  const { root, run } = fixture(t);
  rmSync(path.join(root, 'public/source'), { recursive: true });
  assert.notEqual(run().status, 0);
  const optional = run('--optional');
  assert.equal(optional.status, 0, optional.stderr);
});

test('rejects symlinks in published source metadata', t => {
  const { root, run } = fixture(t);
  const filename = path.join(root, 'public/source/manifest.json');
  const renamed = path.join(root, 'manifest.json');
  require('node:fs').renameSync(filename, renamed);
  symlinkSync(renamed, filename);
  const result = run();
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /symlink/);
});
