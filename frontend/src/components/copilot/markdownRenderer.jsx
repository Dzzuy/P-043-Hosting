import React from 'react';

export function renderInlineWithCitations(text, citations = [], onCitationClick) {
  if (!text) return null;
  const parts = text.split(/(\[C\d+\])/g);
  return parts.map((part, index) => {
    const match = part.match(/^\[(C\d+)\]$/);
    if (match) {
      const cid = match[1];
      const cite = citations.find((c) => c.citation_id === cid);
      const title = cite?.title || cite?.document_id || cid;
      const displayTitle = title.length > 26 ? title.slice(0, 26) + '…' : title;
      return (
        <button
          key={`cite-${index}`}
          type="button"
          onClick={() => onCitationClick && onCitationClick(cite || { citation_id: cid, title })}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            padding: '1px 6px',
            margin: '0 3px',
            borderRadius: 5,
            backgroundColor: '#EFF6FF',
            border: '1px solid #BFDBFE',
            color: '#1D4ED8',
            fontSize: '0.76rem',
            fontWeight: 600,
            cursor: 'pointer',
            verticalAlign: 'baseline',
            transition: 'all 0.15s ease',
          }}
          title={cite ? `${cite.title || cite.document_id} (${cite.version || ''})` : cid}
        >
          <span>📄 {displayTitle}</span>
        </button>
      );
    }
    return renderFormattedText(part, index);
  });
}

export function renderFormattedText(text, keyPrefix) {
  const boldParts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return boldParts.map((bPart, bIdx) => {
    if (bPart.startsWith('**') && bPart.endsWith('**')) {
      return <strong key={`${keyPrefix}-b-${bIdx}`}>{bPart.slice(2, -2)}</strong>;
    }
    if (bPart.startsWith('*') && bPart.endsWith('*')) {
      return <em key={`${keyPrefix}-i-${bIdx}`}>{bPart.slice(1, -1)}</em>;
    }
    const codeParts = bPart.split(/(`[^`]+`)/g);
    return codeParts.map((cPart, cIdx) => {
      if (cPart.startsWith('`') && cPart.endsWith('`')) {
        return (
          <code
            key={`${keyPrefix}-c-${cIdx}`}
            style={{
              backgroundColor: '#F3F4F6',
              padding: '1px 5px',
              borderRadius: 4,
              fontSize: '0.85em',
              fontFamily: 'monospace',
            }}
          >
            {cPart.slice(1, -1)}
          </code>
        );
      }
      return cPart;
    });
  });
}

export function renderMarkdownWithCitations(content, citations = [], onCitationClick) {
  if (!content) return null;
  const lines = content.split('\n');
  const elements = [];
  let tableRows = [];
  let listItems = [];
  let listType = null;

  const flushTable = () => {
    if (tableRows.length > 0) {
      const headerRow = tableRows[0];
      const hasSeparator = tableRows.length > 1 && /^\|?(\s*:?-+:?\s*\|?)+$/.test(tableRows[1].trim());
      const bodyRows = hasSeparator ? tableRows.slice(2) : tableRows.slice(1);

      const parseCells = (row) =>
        row
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map((c) => c.trim());

      const headers = parseCells(headerRow);

      elements.push(
        <div key={`table-${elements.length}`} style={{ overflowX: 'auto', margin: '12px 0' }}>
          <table
            style={{
              width: '100%',
              borderCollapse: 'collapse',
              fontSize: '0.84rem',
              border: '1px solid #E5E7EB',
            }}
          >
            <thead>
              <tr style={{ backgroundColor: '#F9FAFB' }}>
                {headers.map((h, i) => (
                  <th
                    key={i}
                    style={{
                      padding: '8px 12px',
                      border: '1px solid #E5E7EB',
                      textAlign: 'left',
                      fontWeight: 700,
                      color: '#111827',
                    }}
                  >
                    {renderInlineWithCitations(h, citations, onCitationClick)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {bodyRows.map((r, rIdx) => {
                const cells = parseCells(r);
                return (
                  <tr key={rIdx} style={{ backgroundColor: rIdx % 2 === 1 ? '#FAFAFA' : '#FFFFFF' }}>
                    {cells.map((cell, cIdx) => (
                      <td
                        key={cIdx}
                        style={{
                          padding: '8px 12px',
                          border: '1px solid #E5E7EB',
                          color: '#374151',
                        }}
                      >
                        {renderInlineWithCitations(cell, citations, onCitationClick)}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      );
      tableRows = [];
    }
  };

  const flushList = () => {
    if (listItems.length > 0) {
      if (listType === 'ol') {
        elements.push(
          <ol key={`ol-${elements.length}`} style={{ paddingLeft: 22, margin: '8px 0', fontSize: '0.9rem' }}>
            {listItems.map((item, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                {renderInlineWithCitations(item, citations, onCitationClick)}
              </li>
            ))}
          </ol>
        );
      } else {
        elements.push(
          <ul key={`ul-${elements.length}`} style={{ paddingLeft: 20, margin: '8px 0', fontSize: '0.9rem' }}>
            {listItems.map((item, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                {renderInlineWithCitations(item, citations, onCitationClick)}
              </li>
            ))}
          </ul>
        );
      }
      listItems = [];
      listType = null;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.startsWith('|') && trimmed.endsWith('|') && trimmed.length > 2) {
      flushList();
      tableRows.push(trimmed);
      continue;
    } else {
      flushTable();
    }

    if (/^[-*]\s+/.test(trimmed)) {
      if (listType === 'ol') flushList();
      listType = 'ul';
      listItems.push(trimmed.replace(/^[-*]\s+/, ''));
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      if (listType === 'ul') flushList();
      listType = 'ol';
      listItems.push(trimmed.replace(/^\d+\.\s+/, ''));
      continue;
    }

    flushList();

    if (!trimmed) {
      continue;
    }

    if (trimmed.startsWith('### ')) {
      elements.push(
        <h4 key={`h4-${elements.length}`} style={{ fontSize: '0.95rem', fontWeight: 700, margin: '14px 0 6px 0', color: '#111827' }}>
          {renderInlineWithCitations(trimmed.slice(4), citations, onCitationClick)}
        </h4>
      );
      continue;
    }
    if (trimmed.startsWith('## ')) {
      elements.push(
        <h3 key={`h3-${elements.length}`} style={{ fontSize: '1.02rem', fontWeight: 800, margin: '16px 0 8px 0', color: '#111827' }}>
          {renderInlineWithCitations(trimmed.slice(3), citations, onCitationClick)}
        </h3>
      );
      continue;
    }
    if (trimmed.startsWith('# ')) {
      elements.push(
        <h2 key={`h2-${elements.length}`} style={{ fontSize: '1.12rem', fontWeight: 800, margin: '18px 0 10px 0', color: '#111827' }}>
          {renderInlineWithCitations(trimmed.slice(2), citations, onCitationClick)}
        </h2>
      );
      continue;
    }

    elements.push(
      <p key={`p-${elements.length}`} style={{ margin: '6px 0', lineHeight: 1.6 }}>
        {renderInlineWithCitations(line, citations, onCitationClick)}
      </p>
    );
  }

  flushTable();
  flushList();

  return <>{elements}</>;
}
