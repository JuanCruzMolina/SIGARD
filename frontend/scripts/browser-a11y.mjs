// Basic, automatable accessibility checks for browser tests (not a substitute for a screen
// reader review): accessible names of visible controls, WCAG AA text contrast against the
// effective background, and keyboard reachability with Tab.

// Returns { unnamed: [...], lowContrast: [...] } for the visible content of `container`.
export function auditAccessibility(page, container = 'body') {
  return page.evaluate(selector => {
    const root = document.querySelector(selector)
    if (!root) return { missing: selector, unnamed: [], lowContrast: [] }
    const visible = e => { const r = e.getBoundingClientRect(), s = getComputedStyle(e); return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !e.closest('[aria-hidden="true"]') }
    const nameOf = e => (e.getAttribute('aria-label') || (e.getAttribute('aria-labelledby') || '').split(' ').map(id => document.getElementById(id)?.textContent || '').join(' ')
      || [...(e.labels || [])].map(l => l.textContent).join(' ') || (e.tagName === 'INPUT' && ['submit', 'button'].includes(e.type) ? e.value : '')
      || (['BUTTON', 'A', 'SUMMARY'].includes(e.tagName) ? e.textContent : '') || e.getAttribute('title') || e.querySelector?.('img[alt]')?.alt || '').trim()
    const unnamed = [...root.querySelectorAll('button, a[href], input:not([type="hidden"]), select, textarea, summary, [role="button"], [tabindex="0"]')]
      .filter(e => visible(e) && !e.closest('.leaflet-container') && !nameOf(e))
      .map(e => `${e.tagName.toLowerCase()}${e.className && typeof e.className === 'string' ? '.' + e.className.split(' ')[0] : ''}`)
    const rgba = s => (s.match(/[\d.]+/g) || []).map(Number)
    const mix = (fg, bg) => fg.slice(0, 3).map((v, i) => v * (fg[3] ?? 1) + bg[i] * (1 - (fg[3] ?? 1)))
    const lum = c => c.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0)
    const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05) }
    const background = e => {
      const chain = []; for (let p = e; p; p = p.parentElement) chain.unshift(p)
      let bg = [255, 255, 255]
      for (const p of chain) { const s = getComputedStyle(p); if (s.backgroundImage !== 'none') return null; bg = mix(rgba(s.backgroundColor), bg) }
      return bg
    }
    const lowContrast = []
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode: n => n.textContent.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT })
    const seen = new Set()
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const e = node.parentElement
      if (!e || seen.has(e) || !visible(e) || e.closest('.leaflet-container, svg, [disabled], .pv-sr, .pa-sr, .sr-only')) continue
      seen.add(e)
      const bg = background(e); if (!bg) continue // text over images/gradients is reviewed manually
      const s = getComputedStyle(e)
      const value = ratio(mix(rgba(s.color), bg), bg)
      const large = parseFloat(s.fontSize) >= 24 || (parseFloat(s.fontSize) >= 18.66 && parseInt(s.fontWeight) >= 700)
      if (value < (large ? 3 : 4.5)) lowContrast.push({ text: node.textContent.trim().slice(0, 40), ratio: Number(value.toFixed(2)), class: typeof e.className === 'string' ? e.className : e.tagName })
    }
    return { unnamed, lowContrast }
  }, container)
}

// Presses Tab from the start of the document until `selector` has focus.
export async function tabReaches(page, selector, maxTabs = 80) {
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0) })
  for (let i = 0; i < maxTabs; i++) {
    await page.keyboard.press('Tab')
    if (await page.evaluate(s => document.activeElement?.matches(s), selector)) return i + 1
  }
  return null
}
