/**
 * SERP 搜索引擎结果提取脚本
 *
 * 本文件提供可在 Chrome DevTools MCP 的 evaluate_script 中直接执行的 JavaScript 函数。
 * LLM 使用时，将所需函数体复制到 evaluate_script 的 function 参数中即可。
 *
 * 支持搜索引擎：Google、Bing、Baidu
 * 功能：有机结果提取、广告检测、翻页元素检测
 */

// ============================================================
// 引擎配置：选择器定义
// ============================================================
// 在 evaluate_script 中使用时，直接复制此对象到函数内

const SERP_CONFIG = {
  google: {
    // Google 2025+ 已弃用 div.g，使用以下多层级选择器
    organic: [
      '#rso .MjjYud a[href]',           // 当前主流有机结果容器
      '#rso .g .yuRUbf a[href]',         // 传统备选
      '#rso [data-header-feature] a[href]', // 新版布局
    ],
    ad: [
      '[data-text-ad]',
      '#tads .yuRUbf a[href]',
      '.pla-unit-container a[href]',
      'li.ads-ad',
    ],
    pagination: {
      next: '#pnnext',
      pages: 'table#nav td a',
      indicator: '#navcnt',
    },
    urlExtractor: (el) => el.href,
  },
  bing: {
    organic: [
      '#b_results li.b_algo h2 a[href]',
      '#b_results li.b_algo .b_algo_slug a[href]',
    ],
    ad: [
      'li.b_ad',
      '.b_adSlug',
      '#b_results li.b_adBottom',
    ],
    pagination: {
      next: 'a.sb_pagN',
      pages: 'nav#b_nav a.sb_pagS, nav#b_nav a.sb_pagN',
      indicator: 'nav#b_nav',
    },
    urlExtractor: (el) => {
      const href = el.href;
      if (href && href.includes('bing.com/ck/a?')) {
        try {
          const u = new URL(href).searchParams.get('u');
          if (u && u.length > 2) {
            let b64 = u.substring(2).replace(/-/g, '+').replace(/_/g, '/');
            while (b64.length % 4) b64 += '=';
            const decoded = atob(b64);
            if (decoded.startsWith('http')) return decoded;
          }
        } catch (e) { /* fallback to raw href */ }
      }
      return href;
    },
  },
  baidu: {
    organic: [
      '.result.c-container h3 a[href]',
      '.result-op.c-container h3 a[href]',
      '#content_left .result h3 a[href]',
    ],
    ad: [
      '.ec_wise_ad',
      '.ec_youxuan',
      '.ec_bdtg',
      '#content_left *[class*="ec_"]',
    ],
    pagination: {
      next: 'a.n:last-child',
      pages: '#page a',
      indicator: '#page',
    },
    urlExtractor: (el) => {
      // 百度搜索结果链接可能是百度跳转链接，尝试提取真实 URL
      const href = el.href;
      if (href && href.includes('baidu.com/link')) {
        try {
          const url = new URL(href);
          const realUrl = url.searchParams.get('url');
          if (realUrl && realUrl.startsWith('http')) return decodeURIComponent(realUrl);
        } catch (e) { /* fallback to raw href */ }
      }
      return href;
    },
  },
};

// ============================================================
// 辅助函数：检测当前搜索引擎
// ============================================================
// 在 evaluate_script 中使用时，直接将函数体复制进去

/**
 * 检测当前页面属于哪个搜索引擎
 * 返回: 'google' | 'bing' | 'baidu' | null
 */
function detectSearchEngine() {
  const host = window.location.hostname;
  if (host.includes('google.')) return 'google';
  if (host.includes('bing.')) return 'bing';
  if (host.includes('baidu.')) return 'baidu';
  return null;
}

// ============================================================
// 核心提取函数：提取有机搜索结果 URL
// ============================================================
// evaluate_script 用法示例：
// (function() {
//   <粘贴 detectSearchEngine 函数体>
//   <粘贴 SERP_CONFIG>
//   <粘贴 extractOrganicUrls 函数体>
//   return JSON.stringify(extractOrganicUrls());
// })()

/**
 * 提取当前搜索结果页面的所有有机搜索结果 URL
 * 返回: { engine: string, urls: string[], count: number }
 */
function extractOrganicUrls() {
  const engine = detectSearchEngine();
  if (!engine) return { engine: null, urls: [], count: 0, error: '未识别的搜索引擎' };

  const config = SERP_CONFIG[engine];
  const urls = new Set();
  const adUrls = new Set();

  // 先收集广告 URL，用于排除
  for (const selector of config.ad) {
    document.querySelectorAll(selector).forEach(el => {
      const link = el.querySelector('a[href]');
      if (link && link.href) adUrls.add(link.href);
    });
  }

  // 收集有机结果 URL
  for (const selector of config.organic) {
    document.querySelectorAll(selector).forEach(el => {
      const url = config.urlExtractor(el);
      if (url && !adUrls.has(url) && url.startsWith('http')) {
        urls.add(url);
      }
    });
  }

  return {
    engine,
    urls: Array.from(urls),
    count: urls.size,
  };
}

// ============================================================
// 翻页检测函数
// ============================================================
// evaluate_script 用法：
// (function() {
//   <粘贴 detectSearchEngine 函数体>
//   <粘贴 SERP_CONFIG>
//   <粘贴 detectPagination 函数体>
//   return JSON.stringify(detectPagination());
// })()

/**
 * 检测搜索结果页面的翻页信息
 * 返回: { hasNext: boolean, nextUrl: string|null, currentPage: number|null, totalPages: number|null }
 */
function detectPagination() {
  const engine = detectSearchEngine();
  if (!engine) return { hasNext: false, nextUrl: null, currentPage: null, totalPages: null };

  const config = SERP_CONFIG[engine].pagination;

  // 检测是否有下一页
  const nextEl = document.querySelector(config.next);
  const hasNext = !!nextEl;
  const nextUrl = nextEl ? nextEl.href : null;

  // 尝试获取页码信息
  const pageEls = document.querySelectorAll(config.pages);
  let currentPage = null;
  let totalPages = null;

  if (pageEls.length > 0) {
    const pageNumbers = [];
    pageEls.forEach(el => {
      const num = parseInt(el.textContent.trim());
      if (!isNaN(num)) pageNumbers.push(num);
      if (el.classList.contains('sb_pagS') || el.getAttribute('aria-current')) {
        currentPage = num;
      }
    });
    if (pageNumbers.length > 0) {
      totalPages = Math.max(...pageNumbers);
    }
  }

  return { hasNext, nextUrl, currentPage, totalPages };
}

// ============================================================
// 完整 SERP 提取（一次性获取所有信息）
// ============================================================
// evaluate_script 用法：
// (function() {
//   <粘贴所有函数和配置>
//   return JSON.stringify(extractFullSerp());
// })()

/**
 * 一次性提取 SERP 完整信息
 * 返回: { engine, urls, urlCount, ads, adCount, pagination, query }
 */
function extractFullSerp() {
  const engine = detectSearchEngine();
  if (!engine) return { engine: null, error: '未识别的搜索引擎' };

  const config = SERP_CONFIG[engine];
  const adUrls = new Set();

  // 收集广告
  for (const selector of config.ad) {
    document.querySelectorAll(selector).forEach(el => {
      const link = el.querySelector('a[href]');
      if (link && link.href) adUrls.add(link.href);
    });
  }

  // 收集有机结果
  const urls = new Set();
  for (const selector of config.organic) {
    document.querySelectorAll(selector).forEach(el => {
      const url = config.urlExtractor(el);
      if (url && !adUrls.has(url) && url.startsWith('http')) {
        urls.add(url);
      }
    });
  }

  // 翻页信息
  const nextEl = document.querySelector(config.pagination.next);
  const pagination = {
    hasNext: !!nextEl,
    nextUrl: nextEl ? nextEl.href : null,
  };

  // 搜索词
  let query = '';
  const searchInput = document.querySelector('input[name="q"]') ||
                      document.querySelector('textarea[name="q"]');
  if (searchInput) query = searchInput.value;

  return {
    engine,
    urls: Array.from(urls),
    urlCount: urls.size,
    ads: Array.from(adUrls),
    adCount: adUrls.size,
    pagination,
    query,
  };
}
