import hljs from 'highlight.js/lib/core';
import bash from 'highlight.js/lib/languages/bash';
import cpp from 'highlight.js/lib/languages/cpp';
import go from 'highlight.js/lib/languages/go';
import java from 'highlight.js/lib/languages/java';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import python from 'highlight.js/lib/languages/python';
import rust from 'highlight.js/lib/languages/rust';
import typescript from 'highlight.js/lib/languages/typescript';
import katex from 'katex';
import MarkdownIt from 'markdown-it';

hljs.registerLanguage('bash', bash);
hljs.registerLanguage('cpp', cpp);
hljs.registerLanguage('go', go);
hljs.registerLanguage('java', java);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('python', python);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('typescript', typescript);
hljs.registerAliases(['c', 'cc', 'c++', 'h', 'hpp'], { languageName: 'cpp' });
hljs.registerAliases(['js'], { languageName: 'javascript' });
hljs.registerAliases(['py'], { languageName: 'python' });
hljs.registerAliases(['sh', 'shell', 'powershell', 'ps1'], { languageName: 'bash' });
hljs.registerAliases(['ts'], { languageName: 'typescript' });

function escapeHtml(value: string): string {
  return value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function renderMath(source: string, displayMode: boolean): string {
  return katex.renderToString(source, {
    displayMode,
    output: 'html',
    strict: 'ignore',
    throwOnError: false,
    trust: false,
  });
}

function mathBlock(state: any, startLine: number, endLine: number, silent: boolean): boolean {
  const lineStart = state.bMarks[startLine] + state.tShift[startLine];
  const lineEnd = state.eMarks[startLine];
  const firstLine = state.src.slice(lineStart, lineEnd);
  const isDollar = firstLine.startsWith('$$');
  const isBracket = firstLine.startsWith('\\[');

  if (!isDollar && !isBracket) return false;
  if (silent) return true;

  const openMarker = isDollar ? '$$' : '\\[';
  const closeMarker = isDollar ? '$$' : '\\]';
  let content = firstLine.slice(openMarker.length);
  let nextLine = startLine;
  let found = false;

  const inlineClose = content.indexOf(closeMarker);
  if (inlineClose >= 0) {
    content = content.slice(0, inlineClose);
    found = true;
  } else {
    while (++nextLine < endLine) {
      const currentStart = state.bMarks[nextLine] + state.tShift[nextLine];
      const currentEnd = state.eMarks[nextLine];
      const currentLine = state.src.slice(currentStart, currentEnd);
      const closeIndex = currentLine.indexOf(closeMarker);

      if (closeIndex >= 0) {
        content += `\n${currentLine.slice(0, closeIndex)}`;
        found = true;
        break;
      }

      content += `\n${currentLine}`;
    }
  }

  if (!found) return false;

  const token = state.push('math_block', 'math', 0);
  token.block = true;
  token.content = content.trim();
  token.map = [startLine, nextLine + 1];
  state.line = nextLine + 1;
  return true;
}

function mathInline(state: any, silent: boolean): boolean {
  if (state.src.startsWith('\\(', state.pos)) {
    const close = state.src.indexOf('\\)', state.pos + 2);
    if (close <= state.pos + 2) return false;
    if (!silent) {
      const token = state.push('math_inline', 'math', 0);
      token.content = state.src.slice(state.pos + 2, close).trim();
    }
    state.pos = close + 2;
    return true;
  }

  if (state.src[state.pos] !== '$' || state.src[state.pos + 1] === '$') return false;

  let close = state.pos + 1;
  while ((close = state.src.indexOf('$', close)) >= 0) {
    if (state.src[close - 1] !== '\\') break;
    close += 1;
  }

  if (close <= state.pos + 1) return false;
  const content = state.src.slice(state.pos + 1, close).trim();
  if (!content) return false;

  if (!silent) {
    const token = state.push('math_inline', 'math', 0);
    token.content = content;
  }
  state.pos = close + 1;
  return true;
}

function mathPlugin(md: MarkdownIt): void {
  md.block.ruler.before('fence', 'math_block', mathBlock, {
    alt: ['paragraph', 'reference', 'blockquote', 'list'],
  });
  md.inline.ruler.after('escape', 'math_inline', mathInline);
  md.renderer.rules.math_inline = (tokens: any[], index: number): string => renderMath(tokens[index].content, false);
  md.renderer.rules.math_block = (tokens: any[], index: number): string =>
    `<div class="math-display">${renderMath(tokens[index].content, true)}</div>\n`;
}

function highlightCode(source: string, language: string): string {
  const normalizedLanguage = language.trim().toLowerCase();
  if (normalizedLanguage && hljs.getLanguage(normalizedLanguage)) {
    try {
      const highlighted = hljs.highlight(source, {
        language: normalizedLanguage,
        ignoreIllegals: true,
      }).value;
      return `<pre class="hljs"><code>${highlighted}</code></pre>`;
    } catch {
      return `<pre class="hljs"><code>${escapeHtml(source)}</code></pre>`;
    }
  }

  return `<pre class="hljs"><code>${escapeHtml(source)}</code></pre>`;
}

const markdown = new MarkdownIt({
  breaks: false,
  html: false,
  linkify: true,
  typographer: true,
  highlight: highlightCode,
});

markdown.use(mathPlugin);

const defaultLinkOpen = markdown.renderer.rules.link_open;
markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  const token = tokens[index];
  const href = token.attrGet('href') ?? '';
  if (/^https?:\/\//i.test(href)) {
    token.attrSet('target', '_blank');
    token.attrSet('rel', 'nofollow noopener noreferrer');
  }
  return defaultLinkOpen ? defaultLinkOpen(tokens, index, options, env, self) : self.renderToken(tokens, index, options);
};

export function renderMarkdown(source: string): string {
  const normalizedSource = source.trim();
  if (!normalizedSource) return '';
  return markdown.render(normalizedSource);
}
