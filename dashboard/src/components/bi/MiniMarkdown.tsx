import { Fragment } from "react";

// A small, safe markdown renderer for the agents' text (LLM output): headings,
// paragraphs, bullet/numbered lists, pipe tables, **bold**, *italic*, `code`
// and [links](https://...). Builds React elements -- never injects HTML.

function inline(text: string, keyBase: string) {
  const parts = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|\[[^\]]+\]\((https?:\/\/[^)\s]+)\))/g;
  let last = 0;
  let m;
  let i = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    const key = `${keyBase}-${i++}`;
    if (tok.startsWith("**")) parts.push(<strong key={key} className="font-semibold text-slate-100">{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("`")) parts.push(<code key={key} className="rounded bg-slate-800 px-1 text-[0.9em] text-cyan-200">{tok.slice(1, -1)}</code>);
    else if (tok.startsWith("[")) {
      const label = tok.slice(1, tok.indexOf("]"));
      parts.push(
        <a key={key} href={m[2]} target="_blank" rel="noreferrer noopener" className="text-cyan-300 underline-offset-2 hover:underline">
          {label}
        </a>,
      );
    } else parts.push(<em key={key}>{tok.slice(1, -1)}</em>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function MiniMarkdown({ text, className = "" }) {
  if (!text) return null;
  const lines = String(text).replace(/\r/g, "").split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      const size = heading[1].length <= 2 ? "text-base" : "text-sm";
      blocks.push(<p key={i} className={`mt-2 font-display font-semibold text-slate-100 ${size}`}>{inline(heading[2], `h${i}`)}</p>);
      i++;
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && /^\s*\|[\s:|-]+\|\s*$/.test(lines[i + 1])) {
      const cells = (l) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const head = cells(line);
      const body = [];
      i += 2;
      while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) body.push(cells(lines[i++]));
      blocks.push(
        <div key={`t${i}`} className="my-2 overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-700 text-slate-400">
                {head.map((c, j) => <th key={j} className="px-2 py-1 font-medium">{inline(c, `th${i}${j}`)}</th>)}
              </tr>
            </thead>
            <tbody>
              {body.map((r, ri) => (
                <tr key={ri} className="border-b border-slate-800/80">
                  {r.map((c, j) => <td key={j} className="px-2 py-1 text-slate-200">{inline(c, `td${i}${ri}${j}`)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const items = [];
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, ""));
        i++;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={`l${i}`} className={`my-1 space-y-1 pl-5 ${ordered ? "list-decimal" : "list-disc"} marker:text-slate-500`}>
          {items.map((it, j) => <li key={j}>{inline(it, `li${i}${j}`)}</li>)}
        </List>,
      );
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4})\s|^\s*([-*•]|\d+[.)])\s+|^\s*\|/.test(lines[i])) para.push(lines[i++]);
    if (!para.length) {
      para.push(lines[i++]);
    }
    blocks.push(
      <p key={`p${i}`} className="my-1.5">
        {para.map((p, j) => (
          <Fragment key={j}>
            {j > 0 ? " " : null}
            {inline(p, `p${i}${j}`)}
          </Fragment>
        ))}
      </p>,
    );
  }
  return <div className={`text-sm leading-relaxed text-slate-300 ${className}`}>{blocks}</div>;
}
