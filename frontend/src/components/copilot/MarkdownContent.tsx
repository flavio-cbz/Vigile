import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';

interface MarkdownContentProps {
  content: string;
  className?: string;
}

export const MarkdownContent: React.FC<MarkdownContentProps> = ({ content, className = '' }) => {
  if (!content) return null;

  // Split content into blocks (code blocks, blockquotes, lists, paragraphs, headers)
  const blocks: React.ReactNode[] = [];
  const lines = content.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // 1. Fenced Code Block: ```lang ... ```
    if (line.trim().startsWith('```')) {
      const lang = line.trim().slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      const codeText = codeLines.join('\n');
      blocks.push(
        <CodeBlock key={`code-${i}`} code={codeText} language={lang} />
      );
      continue;
    }

    // 2. Blockquote: > ...
    if (line.trim().startsWith('>')) {
      const quoteLines: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('>')) {
        quoteLines.push(lines[i].trim().replace(/^>\s*/, ''));
        i++;
      }
      blocks.push(
        <blockquote
          key={`quote-${i}`}
          className="border-l-2 border-accent-info/70 bg-accent-info/5 pl-3 py-1.5 my-2 rounded-r-md text-text-2 italic text-xs leading-relaxed"
        >
          {quoteLines.map((ql, qidx) => (
            <p key={qidx} className={qidx > 0 ? 'mt-1' : ''}>
              {renderInline(ql)}
            </p>
          ))}
        </blockquote>
      );
      continue;
    }

    // 3. Headings: #, ##, ###
    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      const text = headingMatch[2];
      const headingClass =
        level === 1
          ? 'text-sm font-bold text-text-1 mt-3 mb-1 border-b border-border/40 pb-1'
          : level === 2
          ? 'text-xs font-bold text-text-1 mt-2.5 mb-1'
          : 'text-xs font-semibold text-text-2 mt-2 mb-0.5';
      blocks.push(
        <div key={`heading-${i}`} className={headingClass}>
          {renderInline(text)}
        </div>
      );
      i++;
      continue;
    }

    // 4. Ordered list: 1. 2. ...
    if (/^\d+\.\s+/.test(line.trim())) {
      const listItems: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^\d+\.\s+/, ''));
        i++;
      }
      blocks.push(
        <ol key={`ol-${i}`} className="list-decimal pl-4 my-1.5 space-y-1 text-xs text-text-2 leading-relaxed">
          {listItems.map((item, lidx) => (
            <li key={lidx} className="pl-0.5">
              {renderInline(item)}
            </li>
          ))}
        </ol>
      );
      continue;
    }

    // 5. Unordered list: - or *
    if (/^[-*]\s+/.test(line.trim())) {
      const listItems: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        listItems.push(lines[i].trim().replace(/^[-*]\s+/, ''));
        i++;
      }
      blocks.push(
        <ul key={`ul-${i}`} className="list-disc pl-4 my-1.5 space-y-1 text-xs text-text-2 leading-relaxed">
          {listItems.map((item, lidx) => (
            <li key={lidx} className="pl-0.5">
              {renderInline(item)}
            </li>
          ))}
        </ul>
      );
      continue;
    }

    // 6. Empty line
    if (!line.trim()) {
      i++;
      continue;
    }

    // 7. Regular paragraph (gather consecutive non-empty lines)
    const paraLines: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !lines[i].trim().startsWith('```') &&
      !lines[i].trim().startsWith('>') &&
      !lines[i].match(/^#{1,4}\s+/) &&
      !/^\d+\.\s+/.test(lines[i].trim()) &&
      !/^[-*]\s+/.test(lines[i].trim())
    ) {
      paraLines.push(lines[i]);
      i++;
    }

    blocks.push(
      <p key={`p-${i}`} className="my-1.5 text-xs text-text-2 leading-relaxed [overflow-wrap:anywhere]">
        {paraLines.map((pl, pidx) => (
          <React.Fragment key={pidx}>
            {pidx > 0 && <br />}
            {renderInline(pl)}
          </React.Fragment>
        ))}
      </p>
    );
  }

  return <div className={`markdown-body space-y-1 text-xs font-sans ${className}`}>{blocks}</div>;
};

/**
 * Render code block with language header and copy button
 */
const CodeBlock: React.FC<{ code: string; language?: string }> = ({ code, language }) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-border/60 bg-surface-3/60 font-mono text-[11.5px] shadow-sm">
      <div className="flex items-center justify-between px-3 py-1.5 bg-surface-3 border-b border-border/40 text-[10px] text-text-3 font-semibold uppercase tracking-wider">
        <span>{language || 'code'}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-text-3 hover:text-text-1 transition-colors cursor-pointer"
          title="Copier le code"
        >
          {copied ? (
            <>
              <Check className="w-3 h-3 text-status-online" />
              <span className="text-status-online text-[10px]">Copié</span>
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              <span className="text-[10px]">Copier</span>
            </>
          )}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-text-1 leading-normal whitespace-pre">
        <code>{code}</code>
      </pre>
    </div>
  );
};

/**
 * Parses inline formatting: **bold**, *italic*, `code`, and [links](url)
 */
function renderInline(text: string): React.ReactNode[] {
  // Regex tokenizes: code blocks, bold, italic, links
  const tokenRegex = /(`[^`]+`)|(\*\*.*?\*\*)|(__.*?__)|(\*[^*]+\*)|(_[^_]+_)|(\[[^\]]+\]\([^)]+\))/g;
  const nodes: React.ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenRegex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.substring(lastIndex, match.index));
    }

    const matchText = match[0];

    // Inline code: `...`
    if (matchText.startsWith('`') && matchText.endsWith('`')) {
      nodes.push(
        <code
          key={match.index}
          className="font-mono text-[11px] bg-surface-3/80 text-accent-info-strong border border-border/50 px-1 py-0.5 rounded font-semibold break-all"
        >
          {matchText.slice(1, -1)}
        </code>
      );
    }
    // Bold: **...** or __...__
    else if (
      (matchText.startsWith('**') && matchText.endsWith('**')) ||
      (matchText.startsWith('__') && matchText.endsWith('__'))
    ) {
      nodes.push(
        <strong key={match.index} className="font-bold text-text-1">
          {matchText.slice(2, -2)}
        </strong>
      );
    }
    // Italic: *...* or _..._
    else if (
      (matchText.startsWith('*') && matchText.endsWith('*')) ||
      (matchText.startsWith('_') && matchText.endsWith('_'))
    ) {
      nodes.push(
        <em key={match.index} className="italic text-text-2">
          {matchText.slice(1, -1)}
        </em>
      );
    }
    // Link: [text](url)
    else if (matchText.startsWith('[') && matchText.includes('](')) {
      const linkMatch = matchText.match(/\[([^\]]+)\]\(([^)]+)\)/);
      if (linkMatch) {
        nodes.push(
          <a
            key={match.index}
            href={linkMatch[2]}
            target="_blank"
            rel="noopener noreferrer"
            className="text-accent-info hover:underline font-semibold"
          >
            {linkMatch[1]}
          </a>
        );
      } else {
        nodes.push(matchText);
      }
    } else {
      nodes.push(matchText);
    }

    lastIndex = match.index + matchText.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.substring(lastIndex));
  }

  return nodes.length > 0 ? nodes : [text];
}
