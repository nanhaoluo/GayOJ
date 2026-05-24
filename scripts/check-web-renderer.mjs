import assert from 'node:assert/strict';
import { renderMarkdown } from '../apps/web/src/services/markdown.ts';

const sample = [
  '# Renderer Smoke',
  '',
  'Use inline math $a^2 + b^2 = c^2$ and block math:',
  '',
  '$$',
  '\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}',
  '$$',
  '',
  '| Input | Output |',
  '| --- | --- |',
  '| `1 2` | `3` |',
  '',
  '```cpp',
  'int main() { return 0; }',
  '```',
  '',
  '<script>alert("xss")</script>',
].join('\n');

const html = renderMarkdown(sample);

assert.match(html, /<h1>Renderer Smoke<\/h1>/, 'heading should render');
assert.match(html, /class="katex"/, 'KaTeX markup should render');
assert.match(html, /<table>/, 'markdown table should render');
assert.match(html, /<pre class="hljs"><code>/, 'code fence should render as highlighted block');
assert.ok(!html.includes('<script>'), 'raw HTML script tags must not pass through');
assert.match(html, /&lt;script&gt;alert/, 'raw HTML should be escaped in public problem statements');

console.log('web renderer smoke passed');
