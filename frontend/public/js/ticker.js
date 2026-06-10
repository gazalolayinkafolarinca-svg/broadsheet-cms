/* ============================================================
   THE BROADSHEET — js/ticker.js
   Live market ticker using CoinGecko public API.
   ============================================================ */

'use strict';

const TICKER = (() => {
  const COINS = [
    { id: 'bitcoin',  sym: 'BTC' },
    { id: 'ethereum', sym: 'ETH' },
    { id: 'solana',   sym: 'SOL' },
    { id: 'ripple',   sym: 'XRP' },
    { id: 'sui',      sym: 'SUI' },
  ];

  const STATIC = [
    { sym: 'S&P 500',   price: 6842,   change:  0.4  },
    { sym: 'NASDAQ',    price: 21430,  change:  0.7  },
    { sym: 'FTSE 100',  price: 9104,   change: -0.2  },
    { sym: 'Gold',      price: 3280,   change:  0.3  },
    { sym: 'Oil/Brent', price: 76.40,  change: -0.8  },
    { sym: 'EUR/USD',   price: 1.1124, change:  0.1  },
    { sym: 'USD/NGN',   price: 1615,   change: -0.3  },
  ];

  const FALLBACK = [
    { sym: 'BTC',  price: 185240,   change:  2.4 },
    { sym: 'ETH',  price: 5810,     change:  1.8 },
    { sym: 'SOL',  price: 312.40,   change: -0.6 },
    { sym: 'XRP',  price: 4.21,     change:  3.1 },
    { sym: 'SUI',  price: 8.74,     change:  5.2 },
    ...STATIC,
  ];

  function fmtPrice(p) {
    if (p < 0.0001)  return p.toFixed(8);
    if (p < 0.01)    return p.toFixed(6);
    if (p < 1)       return p.toFixed(4);
    if (p < 100)     return p.toFixed(2);
    return p.toLocaleString('en-US', { maximumFractionDigits: 2 });
  }

  function fmtChange(pct) {
    if (pct == null) return '';
    const cls  = pct >= 0 ? 'up' : 'down';
    const sign = pct >= 0 ? '▲' : '▼';
    return `<span class="${cls}">${sign}${Math.abs(pct).toFixed(2)}%</span>`;
  }

  function buildHTML(items) {
    const make = i =>
      `<span class="ticker-item"><span class="ticker-sym">${i.sym}</span> $${fmtPrice(i.price)} ${fmtChange(i.change)}</span>`;
    return items.map(make).join('') + items.map(make).join('');
  }

  function render(items) {
    const track = document.getElementById('tickerTrack');
    if (!track) return;
    track.innerHTML = buildHTML(items);
    track.style.animation = 'none';
    void track.offsetHeight;
    track.style.animation = '';
  }

  async function fetchLive() {
    const ids = COINS.map(c => c.id).join(',');
    const url = `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`;
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(8000) });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      const crypto = COINS.filter(c => data[c.id]?.usd != null).map(c => ({
        sym: c.sym, price: data[c.id].usd, change: data[c.id].usd_24h_change ?? null,
      }));
      render([...crypto, ...STATIC]);
    } catch {
      render(FALLBACK);
    }
  }

  function init() {
    render(FALLBACK);
    fetchLive();
    setInterval(fetchLive, 5 * 60 * 1000);
  }

  return { init };
})();
