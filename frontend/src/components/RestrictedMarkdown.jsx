import { parseRestrictedMarkdown } from '../services/preventionContent.mjs'

function Inline({ tokens }) {
  return tokens.map((token, index) => {
    if (token.type === 'strong') return <strong key={index}>{token.text}</strong>
    if (token.type === 'link') return <a key={index} href={token.href} target="_blank" rel="noreferrer noopener">{token.text}</a>
    return <span key={index}>{token.text}</span>
  })
}

// Renders the restricted Markdown subset as React elements; never as raw HTML.
export default function RestrictedMarkdown({ text, listClassName, itemAsParagraph = false }) {
  return parseRestrictedMarkdown(text).map((block, index) => block.type === 'list'
    ? <ul key={index} className={listClassName}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{itemAsParagraph ? <p><Inline tokens={item}/></p> : <Inline tokens={item}/>}</li>)}</ul>
    : <p key={index}><Inline tokens={block.inline}/></p>)
}

export function SectionSource({ section }) {
  if (!section?.source_url) return null
  return <small className="section-source">Fuente: <a href={section.source_url} target="_blank" rel="noreferrer noopener">{section.source_label || 'referencia sanitaria'}</a>{section.version ? ` · versión ${section.version}` : ''}</small>
}
