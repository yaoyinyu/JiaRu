// 用 Playwright 验证生成的 HTML：加载、检查控制台错误、核心 DOM 结构与交互
const path = require('path');
const { chromium } = require('C:\\Users\\YaoYinyu\\AppData\\Local\\npm-cache\\_npx\\31e32ef8478fbf80\\node_modules\\playwright');

(async () => {
  const url = 'file:///C:/Users/YaoYinyu/Downloads/JiaRu_whitepaper_v1.1.465_updated.html';
  const executablePath = 'C:\\Users\\YaoYinyu\\AppData\\Local\\ms-playwright\\chromium-1228\\chrome-win64\\chrome.exe';
  const browser = await chromium.launch({ headless: true, executablePath });
  const page = await browser.newPage();
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push('console.error: ' + msg.text()); });
  page.on('pageerror', err => errors.push('pageerror: ' + err.message));

  await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  await page.waitForTimeout(1200);

  const result = await page.evaluate(() => {
    const q = s => document.querySelectorAll(s).length;
    const has = id => !!document.getElementById(id);
    return {
      h2: q('.document h2'),
      h3: q('.document h3'),
      h4: q('.document h4'),
      tocGroups: q('.toc-group'),
      tocSubLinks: q('.toc-sublink'),
      tableShells: q('.table-shell'),
      codeCards: q('.code-card'),
      codeLines: q('.code-line'),
      statusBadges: q('.status-badge'),
      callouts: q('.callout'),
      searchInput: has('docSearch'),
      semanticPanel: has('semanticSearchResults'),
      progressBar: has('progressBar'),
      backToTop: has('backToTop'),
      currentSection: has('currentSection'),
      sidebarOverlay: has('sidebarOverlay'),
      themeButtons: q('.theme-button'),
      versionLine: document.querySelector('.version-line')?.textContent || '',
      heroVersion: document.querySelector('.meta-row dd')?.textContent || '',
      heroStats: [...document.querySelectorAll('.stat-value')].map(e => e.textContent),
      docTextLen: document.querySelector('.document')?.textContent.length || 0,
      firstChapter: document.querySelector('.document h2')?.id || '',
      lastChapter: [...document.querySelectorAll('.document h2')].pop()?.id || '',
      section42: !!document.getElementById('4-2-editor-图片试色'),
      section5: !!document.getElementById('5-http-api-契约'),
      section112: !!document.getElementById('11-2-暂停交接与恢复进展快照-2026-07-30'),
    };
  });

  // 交互测试：主题切换、搜索
  await page.click('.theme-button[data-theme-value="dark"]');
  const themeDark = await page.evaluate(() => document.documentElement.dataset.theme);
  await page.fill('#docSearch', '训练数据');
  await page.waitForTimeout(600);
  const searchResults = await page.evaluate(() => {
    const panel = document.getElementById('semanticSearchResults');
    return { hidden: panel.hidden, results: panel.querySelectorAll('.semantic-result').length, status: document.getElementById('searchStatus').textContent };
  });
  await page.click('#searchClear');

  console.log(JSON.stringify({ result, themeDark, searchResults, errors }, null, 2));
  await browser.close();
})();
