"use client";

import { Fragment, type ReactNode } from "react";

import { safeHref } from "@/components/common/links";
import { cn } from "@/lib/utils";

/**
 * A small, safe markdown renderer for agent answers.
 *
 * The answer is model output built partly from web content, so it is never treated as HTML:
 * everything becomes React text nodes. Supported: paragraphs, `###` headings, bullet and
 * numbered lists (one nesting level), GFM tables, blockquotes, fenced code, **bold**,
 * *italic*, `code`, http(s) links, and citation markers `[1]` rendered by `renderCitation`.
 */

type RenderCitation = (n: number, key: string) => ReactNode;

type Block =
  | { type: "p"; text: string }
  | { type: "h"; level: number; text: string }
  | { type: "ul" | "ol"; items: { text: string; depth: number }[] }
  | { type: "table"; head: string[]; rows: string[][] }
  | { type: "quote"; text: string }
  | { type: "code"; text: string };

const UL = /^(\s*)[-*+]\s+(.*)$/;
const OL = /^(\s*)\d{1,3}[.)]\s+(.*)$/;
const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

export function parseBlocks(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.trim().startsWith("```")) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) body.push(lines[i++]);
      i++;
      blocks.push({ type: "code", text: body.join("\n") });
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ type: "h", level: heading[1].length, text: heading[2] });
      i++;
      continue;
    }
    if (line.includes("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push({ type: "table", head, rows });
      continue;
    }
    if (UL.test(line) || OL.test(line)) {
      const type = UL.test(line) ? "ul" : "ol";
      const re = type === "ul" ? UL : OL;
      const items: { text: string; depth: number }[] = [];
      while (i < lines.length) {
        const m = re.exec(lines[i]) ?? (type === "ul" ? OL : UL).exec(lines[i]);
        if (m) {
          items.push({ text: m[2], depth: m[1].replace(/\t/g, "  ").length >= 2 ? 1 : 0 });
          i++;
        } else if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) {
          items[items.length - 1].text += ` ${lines[i].trim()}`; // wrapped continuation line
          i++;
        } else {
          break;
        }
      }
      blocks.push({ type, items });
      continue;
    }
    if (line.trim().startsWith(">")) {
      const body: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith(">")) body.push(lines[i++].trim().replace(/^>\s?/, ""));
      blocks.push({ type: "quote", text: body.join(" ") });
      continue;
    }
    const body: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !HEADING.test(lines[i]) &&
      !UL.test(lines[i]) &&
      !OL.test(lines[i]) &&
      !lines[i].trim().startsWith("```") &&
      !lines[i].trim().startsWith(">")
    ) {
      body.push(lines[i++].trim());
    }
    blocks.push({ type: "p", text: body.join(" ") });
  }
  return blocks;
}

// Inline tokens, earliest match wins: code, link, citation run, bold, italic. (`_italic_` is
// deliberately unsupported: snake_case keys like pricing.standard_fee are common in answers.)
const INLINE =
  /(`[^`\n]+`)|\[([^\]\n]{1,300})\]\(([^)\s]{1,2000})\)|((?:\[\d{1,2}(?:\s*,\s*\d{1,2})*\])+)|\*\*([^*\n]+?)\*\*|__([^_\n]+?)__|\*(?![\s*])([^*\n]+?)\*/g;

export function renderInline(text: string, renderCitation: RenderCitation, keyPrefix = "i"): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let index = 0;
  for (const m of text.matchAll(INLINE)) {
    const start = m.index ?? 0;
    if (start > last) out.push(text.slice(last, start));
    const key = `${keyPrefix}-${index++}`;
    if (m[1]) {
      out.push(
        <code key={key} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]">
          {m[1].slice(1, -1)}
        </code>,
      );
    } else if (m[2] !== undefined) {
      const href = safeHref(m[3]);
      const label = renderInline(m[2], renderCitation, key);
      out.push(
        href ? (
          <a
            key={key}
            href={href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-brand underline underline-offset-4"
          >
            {label}
          </a>
        ) : (
          <Fragment key={key}>{label}</Fragment>
        ),
      );
    } else if (m[4]) {
      const numbers = [...m[4].matchAll(/\d{1,2}/g)].map((x) => Number(x[0]));
      out.push(
        <Fragment key={key}>{[...new Set(numbers)].map((n) => renderCitation(n, `${key}-${n}`))}</Fragment>,
      );
    } else if (m[5] ?? m[6]) {
      out.push(
        <strong key={key} className="font-semibold">
          {renderInline((m[5] ?? m[6]) as string, renderCitation, key)}
        </strong>,
      );
    } else if (m[7]) {
      out.push(<em key={key}>{renderInline(m[7], renderCitation, key)}</em>);
    }
    last = start + m[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type AnswerMarkdownProps = {
  markdown: string;
  renderCitation: RenderCitation;
  className?: string;
};

export function AnswerMarkdown({ markdown, renderCitation, className }: AnswerMarkdownProps) {
  const blocks = parseBlocks(markdown);
  const inline = (text: string, key: string) => renderInline(text, renderCitation, key);
  return (
    <div className={cn("space-y-3 text-sm leading-relaxed text-pretty break-words", className)}>
      {blocks.map((block, b) => {
        const key = `b${b}`;
        switch (block.type) {
          case "h":
            return (
              <p
                key={key}
                role="heading"
                aria-level={Math.min(6, block.level + 2)}
                className={cn("font-semibold tracking-tight", block.level <= 2 ? "text-base" : "text-sm")}
              >
                {inline(block.text, key)}
              </p>
            );
          case "ul":
          case "ol": {
            const List = block.type;
            return (
              <List
                key={key}
                className={cn("space-y-1.5 pl-5", block.type === "ul" ? "list-disc" : "list-decimal")}
              >
                {block.items.map((item, n) => (
                  <li key={`${key}-${n}`} className={cn("pl-0.5 marker:text-muted-foreground", item.depth && "ml-5")}>
                    {inline(item.text, `${key}-${n}`)}
                  </li>
                ))}
              </List>
            );
          }
          case "table":
            return (
              <div key={key} className="overflow-x-auto rounded-lg border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted/50">
                    <tr>
                      {block.head.map((cell, c) => (
                        <th key={c} scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                          {inline(cell, `${key}-h${c}`)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r} className="border-t align-top">
                        {block.head.map((_, c) => (
                          <td key={c} className="px-3 py-2">
                            {inline(row[c] ?? "", `${key}-${r}-${c}`)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            );
          case "quote":
            return (
              <blockquote key={key} className="border-l-2 pl-3 text-muted-foreground">
                {inline(block.text, key)}
              </blockquote>
            );
          case "code":
            return (
              <pre key={key} className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs">
                {block.text}
              </pre>
            );
          default:
            return <p key={key}>{inline(block.text, key)}</p>;
        }
      })}
    </div>
  );
}
