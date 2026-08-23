import React from "react";
import DOMPurify from "dompurify";

// Lightweight markdown renderer for chat responses. All generated HTML is
// sanitized with DOMPurify before it reaches dangerouslySetInnerHTML.
function inline(text) {
  let t = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  // ATA citation highlight: [Doc, ATA 74-00-00]
  t = t.replace(/\[([^\]]*ATA[^\]]*)\]/g, '<span class="ata-cite">[$1]</span>');
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return t;
}

// Sanitize to a strict allow-list of inline formatting tags only.
function safe(text) {
  return DOMPurify.sanitize(inline(text), {
    ALLOWED_TAGS: ["span", "code", "strong", "em", "b", "i"],
    ALLOWED_ATTR: ["class"],
  });
}

export default function Markdown({ text }) {
  const lines = (text || "").split("\n");
  const blocks = [];
  let list = null; // {type, items}

  const flush = () => {
    if (list) {
      blocks.push({ type: list.type, items: list.items });
      list = null;
    }
  };

  lines.forEach((raw) => {
    const line = raw.trimEnd();
    const ol = line.match(/^\s*(\d+)\.\s+(.*)$/);
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (ol) {
      if (!list || list.type !== "ol") { flush(); list = { type: "ol", items: [] }; }
      list.items.push(ol[2]);
    } else if (ul) {
      if (!list || list.type !== "ul") { flush(); list = { type: "ul", items: [] }; }
      list.items.push(ul[1]);
    } else if (h) {
      flush();
      blocks.push({ type: "h", level: h[1].length, text: h[2] });
    } else if (line.trim() === "") {
      flush();
    } else {
      flush();
      blocks.push({ type: "p", text: line });
    }
  });
  flush();

  return (
    <div className="mkd text-[0.95rem] text-foreground/90">
      {blocks.map((b, i) => {
        if (b.type === "h") {
          const Tag = `h${Math.min(b.level + 1, 4)}`;
          return React.createElement(Tag, { key: i, dangerouslySetInnerHTML: { __html: safe(b.text) } });
        }
        if (b.type === "p")
          return <p key={i} dangerouslySetInnerHTML={{ __html: safe(b.text) }} />;
        if (b.type === "ol")
          return (
            <ol key={i}>
              {b.items.map((it, j) => (
                <li key={j} className="animate-step-in" style={{ animationDelay: `${j * 40}ms` }} dangerouslySetInnerHTML={{ __html: safe(it) }} />
              ))}
            </ol>
          );
        return (
          <ul key={i}>
            {b.items.map((it, j) => (
              <li key={j} dangerouslySetInnerHTML={{ __html: safe(it) }} />
            ))}
          </ul>
        );
      })}
    </div>
  );
}
